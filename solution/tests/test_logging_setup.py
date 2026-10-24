"""Logging bootstrap tests; no camera, Qt, or QR model required."""
import io
import logging
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import logging_setup


class LoggingSetupTests(unittest.TestCase):
    def tearDown(self):
        logging_setup.shutdown_logging()

    def test_writes_child_logs_to_console_and_rotating_utf8_file_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            stream = io.StringIO()
            logger = logging_setup.setup_logging(Path(tmp), stream=stream)
            same = logging_setup.setup_logging(Path(tmp), stream=stream)
            self.assertIs(logger, same)
            logging.getLogger("solution.camera").warning("kiểm tra camera")
            for handler in logger.handlers:
                handler.flush()
            text = stream.getvalue()
            file_text = (Path(tmp) / "camera.log").read_text(encoding="utf-8")
            self.assertEqual(text.count("kiểm tra camera"), 1)
            self.assertEqual(file_text.count("kiểm tra camera"), 1)
            rotating = [h for h in logger.handlers
                        if hasattr(h, "maxBytes") and hasattr(h, "backupCount")]
            self.assertEqual(len(rotating), 1)
            self.assertEqual((rotating[0].maxBytes, rotating[0].backupCount),
                             (2 * 1024 * 1024, 3))
            logging_setup.shutdown_logging()

    def test_file_failure_keeps_console_logging(self):
        with tempfile.TemporaryDirectory() as tmp:
            not_a_directory = Path(tmp) / "occupied"
            not_a_directory.write_text("file", encoding="utf-8")
            stream = io.StringIO()
            logger = logging_setup.setup_logging(not_a_directory, stream=stream)
            logging.getLogger("solution.ui").error("console remains available")
            self.assertIn("console remains available", stream.getvalue())
            self.assertEqual(len(logger.handlers), 1)


if __name__ == "__main__":
    unittest.main()
