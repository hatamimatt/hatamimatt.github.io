# Adding writing

The site has no build step: edit these files, commit, and push. GitHub Actions republishes
the site within a few minutes.

## An article written here

1. Write it in Markdown as `articles/<slug>.md`, for example `articles/taylor-diagrams.md`.
   Start with the body; the title, summary and date come from the list below. Images go in
   `assets/articles/` and are referenced as `assets/articles/<file>`.
2. Add an entry to the top of `articles/index.json`:

   ```json
   {
     "slug": "taylor-diagrams",
     "title": "Understanding Taylor Diagrams",
     "dek": "One sentence that tells the reader what they will learn.",
     "date": "2026-11-15",
     "minutes": 8,
     "tags": ["Model validation", "Visualization"],
     "image": "assets/articles/taylor-diagrams.jpg"
   }
   ```

   The newest article (by `date`) leads the Writing section on the homepage. `image` is
   optional; a 3:2 image works best.

## A LinkedIn article, or any page elsewhere

Add an entry with `url` instead of a Markdown file. `kind` is shown in place of the reading time:

```json
{ "slug": "my-linkedin-article", "title": "…", "dek": "…", "date": "2026-11-20",
  "kind": "LinkedIn article", "tags": ["…"], "url": "https://www.linkedin.com/pulse/…" }
```
