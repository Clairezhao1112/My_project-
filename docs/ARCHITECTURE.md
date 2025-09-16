This project scrapes RateMyProfessor data for NYU professors and turns it into course-by-semester rating trends. The system has three main scripts:

1. scraper.py – collects raw reviews from RMP using GraphQL.
2. validators.py – cleans and validates the raw ratings.
3. transformers.py – aggregates reviews into trends and generates insights.

---

Responsibilities
1. scraper.py - Finds the top professors at NYU by number of ratings. Pulls up to 300 ratings per professor (date, rating, course).
2. validators.py - Ensures ratings are between 0–5. Normalizes course codes and removes duplicates.
3. transformers.py - Groups ratings into course × semester buckets. Calculates average ratings per term, review counts, slopes, and momentum.
