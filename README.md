Executive Summary
Picking classes at NYU can feel like guesswork. Students rely on RateMyProfessor reviews, but the site only shows overall ratings, so it’s hard to see how a professor’s reputation changes over time. Our project solves this by scraping public RMP reviews for NYU professors, cleaning the data, and turning it into time-based trends. This gives students an easy way to see if a professor is improving, staying consistent, or trending downward before they register.  

For just $1 per semester, students get access to these insights in a simple, visual format. Advisors and departments could also use the aggregated data to better understand demand and help with course planning.  

---

Technical Architecture Flow Chart
Professor list -> Scraper (HTML fetch + parse) -> Raw JSONL -> Validator -> Clean data (CSV) -> Trend charts

---

Setup and Deployment Instructions
# Pick a parent folder (create one if you like)
mkdir -p ~/Projects && cd ~/Projects

# Clone (this creates a new folder named "My_project-")
git clone https://github.com/Clairezhao1112/My_project-.git

# Open the folder in VS Code
code My_project-   # if 'code' command is installed
# or: File → Open Folder… → select ~/Projects/My_project-


