import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import import_puzzles as importer


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.csv = Path(self.temp.name) / "puzzles.csv"
        self.content = Path(self.temp.name) / "posts"

    def sheet(self, entries):
        with self.csv.open("w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=["Puzzle Number", "Title", "Setter", "Constraints", "Puzzle Link", "Video Link"])
            writer.writeheader()
            for number, title in entries:
                writer.writerow({"Puzzle Number": number, "Title": title, "Setter": "Alice", "Constraints": "Killer Cages, Palindrome Lines", "Puzzle Link": f"https://sudokupad.app/adventure/{number}", "Video Link": "https://youtu.be/bl_WXtLhOXc"})

    def run_import(self, mode):
        with patch.object(sys, "argv", ["import_puzzles.py", mode, "--csv", str(self.csv), "--content", str(self.content)]):
            importer.main()

    @patch.object(importer, "published_at", return_value="2023-01-18T12:27:22-08:00")
    def test_import_is_idempotent_and_writes_post(self, published):
        self.sheet([("1", "Which Way?"), ("1", "Which Way?"), ("2", "Next Puzzle")])
        self.run_import("import")
        post = (self.content / "1-which-way.md").read_text()
        self.assertIn('title = "Puzzle #1 - Which Way? by Alice"', post)
        self.assertIn('aliases = ["/1/"]', post)
        self.assertIn('tags = ["Killer Cages", "Palindrome Lines"]', post)
        self.assertIn("**[Play this puzzle on SudokuPad](https://sudokupad.app/adventure/1)**", post)
        self.assertIn('{{< youtube id="bl_WXtLhOXc" >}}', post)
        self.run_import("import")
        self.assertEqual(published.call_count, 2)
        self.assertEqual(len(list(self.content.glob("*.md"))), 2)

    @patch.object(importer, "published_at", return_value="2023-01-18T12:27:22-08:00")
    def test_append_stops_at_first_existing_row(self, published):
        self.sheet([("1", "First"), ("2", "Second")])
        self.run_import("import")
        published.reset_mock()
        self.sheet([("1", "First"), ("2", "Second"), ("3", "Third"), ("4", "Fourth")])
        self.run_import("append")
        self.assertEqual(published.call_count, 2)
        self.assertEqual(len(list(self.content.glob("*.md"))), 4)

    @patch.object(importer, "published_at", return_value="2023-01-18T12:27:22-08:00")
    def test_same_number_and_title_with_distinct_links(self, published):
        self.sheet([("100", "One Hundred"), ("100", "One Hundred")])
        text = self.csv.read_text().replace("adventure/100,https://youtu.be", "adventure/100-other,https://youtu.be", 1)
        self.csv.write_text(text)
        self.run_import("import")
        self.assertTrue((self.content / "100-one-hundred.md").exists())
        self.assertTrue((self.content / "100-one-hundred-2.md").exists())
        self.assertIn('slug = "100-one-hundred-2"', (self.content / "100-one-hundred-2.md").read_text())

    def test_distinct_rows_with_same_number(self):
        self.sheet([("120", "Balance"), ("120", "Chimney Sweeps")])
        data = importer.rows(self.csv.read_text())
        self.assertEqual([row["alias"] for row in data], [True, False])
        self.assertEqual(len(data), 2)

    def test_video_validation_and_missing_columns(self):
        with self.assertRaises(ValueError):
            importer.video_id("https://example.com/watch?v=bl_WXtLhOXc")
        with self.assertRaises(ValueError):
            importer.rows("Puzzle Number,Title\n1,Test\n")


if __name__ == "__main__":
    unittest.main()
