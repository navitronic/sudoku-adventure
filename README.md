# Sudoku Adventure

A website archive of Sudoku Adventure puzzles, built from the [public spreadsheet](https://docs.google.com/spreadsheets/d/1y4BYBEuXbzReb_tx3bTUdKwynL2JveL3ob55g6c-D-Y/edit?gid=0#gid=0). Requires Python 3.9+ and Hugo 0.169.0; no Python packages or Hugo theme are needed.

## Import puzzles

```sh
python3 scripts/import_puzzles.py import
```

The first import reads each puzzle's YouTube publication timestamp and writes a Markdown post in `content/puzzles/`. For subsequent spreadsheet updates:

```sh
python3 scripts/import_puzzles.py append
```

Append reads rows from the bottom upward and stops at the first existing post. Import skips existing posts and can resume an interrupted bulk import. Neither mode changes existing posts. The importer fails if it cannot read a video's publication timestamp; rerun it after the video becomes available. The public sheet and YouTube watch pages must be reachable from the machine running the importer. Commit the generated Markdown to deploy it; the Cloudflare build does not import puzzles.

Distinct puzzles sharing a number each get a title-based URL. If their titles are also the same, later rows get a numeric suffix (`-2`, `-3`, etc.). The short URL `/{number}/` redirects to the first row with that number; exact duplicate rows are ignored. If a title changes later, the old post is not updated automatically.

Run `python3 scripts/import_puzzles.py import --csv path/to/sheet.csv` to use a downloaded CSV. `--content path/to/directory` changes the output folder (useful for testing).

## RSS feeds

Subscribe to all puzzles at `/index.xml`, or to a constraint at `/tags/<constraint-slug>/index.xml`. The site links to the main feed and advertises the relevant feed to feed readers on each page.

## Local development

```sh
hugo server
python3 -m unittest discover -s tests
hugo --minify
```

## Cloudflare Pages

Connect this repository as a Cloudflare Pages project. Use the following build settings:

- Framework preset: Hugo
- Build command: `hugo --minify`
- Build output directory: `public`
- Environment variable: `HUGO_VERSION=0.169.0`

Set `baseURL` in `hugo.toml` to the deployed domain if it differs from the default `https://sudoku-adventure.pages.dev/`. Deployments build the committed posts. The [Append puzzles workflow](.github/workflows/append-puzzles.yml) runs daily at 20:00 UTC (and can be started manually from GitHub Actions), commits new posts to `main`, and triggers a Pages deployment through the GitHub integration. Enable GitHub Actions and allow workflows to write repository contents in the repository's Actions settings. A failed import leaves existing posts unchanged; rerun the workflow after the spreadsheet or YouTube video is available.
