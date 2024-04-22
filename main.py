'''
Main module to run the web application.
'''
from flask import Flask, request, render_template, jsonify, send_file
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import threading
import sqlite3
import time
import csv

app = Flask(__name__)
app.debug = True
depth = 0
# function to scrape the search results
def scrape_results(search_term, depth):
    print("Scraping results for:", search_term)
    # set up the selenium webdriver
    service = Service(executable_path='/usr/bin/chromedriver')
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")  # Bypass OS security model, REQUIRED on Linux
    options.add_argument('--remote-debugging-pipe') # for debug pipe
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(service=service, options=options)

    with webdriver.Chrome(service=service, options=options) as driver:
    # set up the base url and query params
      base_url = "https://34.211.108.47/manage/s/global-search/%40uri"
      query_params = {
          "q": search_term,
          "sort": "relevancy",
          "numberOfResults": "10",
          "&f:@f5_document_type":"[Support%20Solution]"
      }
      # build the url with the query params
      url = base_url + "?" + "&".join([f"{key}={value}" for key, value in query_params.items()])

      # Change the User-Agent based on the depth
      if depth == 0:
          options.add_argument("User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
      else:
          options.add_argument("Googlebot/2.1 (+http://www.google.com/bot.html)")

      prefs = {"profile.managed_default_content_settings.images": 2}  #dont download images
      options.add_experimental_option("prefs", prefs)

      # navigate to the url
      driver.get(url)
      # get the page source
      page_source = driver.page_source
      # parse the page source with beautiful soup
      soup = BeautifulSoup(page_source, "html.parser")
      # find all the search results
      search_results = soup.find_all("div", class_="search-result")
      # create a list to store the results
      results = []
      # loop through the search results
      for result in search_results:
          # extract the title, link, and excerpt for each search result
          title = result.find("a", class_="search-result-title").text.strip()
          link = result.find("a", class_="search-result-title")["href"]
          excerpt = result.find("div", class_="search-result-excerpt").text.strip()
          # add the result to the list of results
          results.append({"title": title, "link": link, "excerpt": excerpt})
      # close the webdriver
      driver.quit()
      # return the results
      return results

# function to recursively search the links from the results
def recursive_search(links, depth, max_depth, results):
    # check if the maximum depth has been reached
    if depth > max_depth:
        return
    # loop through the links
    for link in links:
        # check if the user has cancelled the scraping process
        if "cancel" in results and results["cancel"]:
            return
        # set up the selenium webdriver
        #  **** driver = webdriver.Chrome()
        # navigate to the link
        driver.get(link)
        # get the page source
        page_source = driver.page_source
        # parse the page source with beautiful soup
        soup = BeautifulSoup(page_source, "html.parser")
        # find all the links on the page
        page_links = [a["href"] for a in soup.find_all("a", href=True)]
        # add the links to the list of links
        links.extend(page_links)
        # extract the text from the page
        text = soup.get_text()
        # count the number of exact matches
        exact_matches = text.count(results["search_term"])
        # count the number of partial matches
        partial_matches = text.lower().count(results["search_term"].lower())
        # calculate the total word count
        word_count = len(text.split())
        # calculate the average word count
        average_word_count = word_count / len(links)
        # calculate the time per link
        time_per_link = results["total_time"] / len(links)
        # update the statistics
        results["total_links_found"] += len(page_links)
        results["total_exact_matches"] += exact_matches
        results["total_partial_matches"] += partial_matches
        results["links_crawled"] += 1
        results["excerpts_read"] += 1
        results["total_word_count"] += word_count
        results["average_word_count"] = average_word_count
        results["time_per_link"] = time_per_link
        # check if the depth has increased
        if depth > results["depth_reached"]:
            results["depth_reached"] = depth
        # check if the link time is the longest so far
        link_time = time.time() - results["start_time"]
        if link_time > results["longest_link_time"]:
            results["longest_link_time"] = link_time
        # close the webdriver
        driver.quit()
        # recursively search the links on the page
        recursive_search(page_links, depth + 1, max_depth, results)

# function to handle the search request
def handle_search_request(search_term, results):
    # set up the sqlite3 database
    print("Handling search request for:", search_term)
    with sqlite3.connect("results.db") as conn:
        c = conn.cursor()
        # create the results table if it doesn't exist
        c.execute("CREATE TABLE IF NOT EXISTS results (title TEXT, link TEXT, excerpt TEXT)")
        # scrape the search results
        start_time = time.time()
        results = scrape_results(search_term, depth)
        total_time = time.time() - start_time
        # set up the results dictionary
        results_dict = {
            "search_term": search_term,
            "total_links_found": len(results),
            "total_exact_matches": 0,
            "total_partial_matches": 0,
            "total_time": total_time,
            "links_crawled": 0,
            "excerpts_read": 0,
            "depth_reached": 0,
            "total_word_count": 0,
            "average_word_count": 0,
            "time_per_link": 0,
            "longest_link_time": 0,
            "start_time": start_time,
            "cancel": False
        }
        # check if the recursive search checkbox is checked
        if request.form.get("recursive_search"):
            # start the recursive search
            recursive_search([result["link"] for result in results], 0, 2, results_dict)
        # insert the results into the database
        for result in results:
            c.execute("INSERT INTO results VALUES (?, ?, ?)", (result["title"], result["link"], result["excerpt"]))
        # commit the changes to the database
        conn.commit()
        # return the results dictionary
        return results_dict

# route for the search page
@app.route("/", methods=["GET", "POST"])
def search():
    if request.method == "POST":
        # get the search term from the form
        search_term = request.form["search_term"]
        # validate the search term
        if not search_term:
            return render_template("search.html", error="Please enter a search term.")
        # handle the search request
        results_dict = handle_search_request(search_term, depth)
        # render the results page
        return render_template("results.html", results=results_dict)
    else:
        # render the search page
        return render_template("search.html")

# route for cancelling the search
@app.route("/cancel", methods=["POST"])
def cancel():
    # set the cancel flag to True
    results_dict["cancel"] = True
    # return a success message
    return "Success"

# route for exporting the results to a csv file
@app.route("/export/csv", methods=["GET"])
def export_csv():
    # set up the sqlite3 database
    with sqlite3.connect("results.db") as conn:
        c = conn.cursor()
        # select all the results from the database
        c.execute("SELECT * FROM results")
        results = c.fetchall()
        # create the csv file
        with open("results.csv", "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Title", "Link", "Excerpt"])
            for result in results:
                writer.writerow(result)
        # return the csv file
        return send_file("results.csv", as_attachment=True)

# route for exporting the results to a json file
@app.route("/export/json", methods=["GET"])
def export_json():
    # set up the sqlite3 database
    with sqlite3.connect("results.db") as conn:
        c = conn.cursor()
        # select all the results from the database
        c.execute("SELECT * FROM results")
        results = c.fetchall()
        # create the json file
        with open("results.json", "w") as jsonfile:
            json.dump(results, jsonfile)
        # return the json file
        return send_file("results.json", as_attachment=True)

if __name__ == "__main__":
    print("Program started")
    app.run(host="0.0.0.0", port="5000")
