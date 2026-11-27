# Publishing this wiki

This folder holds the pages for the OmniScrape GitHub Wiki. It is not part of the Python package, and this `README.md` is not a wiki page: do not copy it into the wiki.

1. **Create the wiki.** On GitHub open the repository, go to the **Wiki** tab and click **Create the first page**. Save any placeholder; this initialises the wiki's git repository.
2. **Clone the wiki repository.**
   ```bash
   git clone https://github.com/loganathan-ai-dev/Omni-Scrape.wiki.git
   ```
3. **Copy the pages in.** Copy everything in `wiki/` **except this `README.md`** into the clone, overwriting the placeholder `Home.md`. Include `_Sidebar.md` and `_Footer.md`.
4. **Commit and push.**
   ```bash
   cd Omni-Scrape.wiki
   git add -A
   git commit -m "Add OmniScrape wiki"
   git push
   ```

## Notes

- Images use absolute `raw.githubusercontent.com` URLs, for example `https://raw.githubusercontent.com/loganathan-ai-dev/Omni-Scrape/main/docs/assets/logo-mark.png`. They only render once the logo has been pushed to the `main` branch of the repository.
- Pages link to each other with `[[Page Name]]` or `[[Text|Page-Name]]`; file names use hyphens (`Fetching-and-Stealth.md`). Keep them in sync if you rename a page.
- The Benchmarks and Comparison pages copy numbers from the main `README.md`. If you update one, update the other.
