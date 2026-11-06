import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from aiindex.collectors import awesome  # noqa: E402

README = """
# Awesome AI

Some intro text with a [link](https://example.com) that is not a bullet.

- [llama.cpp](https://github.com/ggml-org/llama.cpp) - LLM inference in C/C++
- [Ollama](https://github.com/ollama/ollama) — run models locally
* [vLLM](https://github.com/vllm-project/vllm/): high-throughput serving
1. [A tool](https://example.com/tool) - not on github
- [topics page](https://github.com/topics/llm) - should be ignored
- [llama.cpp](https://github.com/ggml-org/llama.cpp) - duplicate entry
"""


class AwesomeParserTests(unittest.TestCase):
    def setUp(self):
        self.items = awesome.parse_markdown(README, "owner/list")
        self.by_id = {item["id"]: item for item in self.items}

    def test_github_entries_reuse_the_github_id(self):
        self.assertIn("gh:ggml-org/llama.cpp", self.by_id)
        item = self.by_id["gh:ggml-org/llama.cpp"]
        self.assertEqual(item["url"], "https://github.com/ggml-org/llama.cpp")
        self.assertEqual(item["kind"], "repo")
        self.assertEqual(item["description"], "LLM inference in C/C++")

    def test_bullet_styles_and_separators(self):
        self.assertIn("gh:ollama/ollama", self.by_id)
        self.assertIn("gh:vllm-project/vllm", self.by_id)
        self.assertEqual(self.by_id["gh:ollama/ollama"]["description"], "run models locally")

    def test_non_github_links_are_kept_as_curated_entries(self):
        self.assertIn("web:https://example.com/tool", self.by_id)
        self.assertEqual(self.by_id["web:https://example.com/tool"]["kind"], "curated")

    def test_noise_and_duplicates_are_dropped(self):
        self.assertNotIn("gh:topics/llm", self.by_id)
        self.assertEqual(len(self.items), 4)

    def test_provenance_is_recorded(self):
        item = self.by_id["gh:ggml-org/llama.cpp"]
        self.assertEqual(item["sources"], ["awesome"])
        self.assertEqual(item["raw"]["curated_by"], "owner/list")


if __name__ == "__main__":
    unittest.main()
