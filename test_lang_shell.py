import unittest

import lang_shell
import langkit
from langtest import edges, needs_grammar, survey_files


@needs_grammar("bash")
class ShellAdapterTest(unittest.TestCase):
    def _model(self, files):
        return survey_files(self, files)

    def test_source_relative_reaches_lib(self):
        model = self._model({"a.sh": "source ./lib.sh\n", "lib.sh": ""})
        self.assertIn(("a.sh", "lib.sh"), edges(model))

    def test_shebang_dirname_source_reaches_lib(self):
        model = self._model({
            "lib/x.sh": "",
            "bin/tool": '#!/usr/bin/env bash\n. "$(dirname "$0")/../lib/x.sh"\n',
        })
        self.assertIn(("bin/tool", "lib/x.sh"), edges(model))

    def test_bash_source_dir_variable_reaches_y(self):
        model = self._model({
            "y.sh": "",
            "a.sh": 'DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
                    'source "$DIR/y.sh"\n',
        })
        self.assertIn(("a.sh", "y.sh"), edges(model))

    def test_non_literal_sources_reach_nothing(self):
        model = self._model({"a.sh": 'source "$HOME/x.sh"\nsource "$1"\n', "x.sh": ""})
        self.assertEqual(edges(model), set())

    def test_bash_and_dot_slash_give_runs_roads(self):
        model = self._model({"a.sh": "bash scripts/deploy.sh\n./scripts/deploy.sh\n",
                             "scripts/deploy.sh": ""})
        edgeset = edges(model)
        self.assertIn(("a.sh", "scripts/deploy.sh"), edgeset)
        self.assertEqual(model.edges[("a.sh", "scripts/deploy.sh")], 2)

    def test_unique_basename_source(self):
        one = self._model({"a.sh": "source lib.sh\n", "lib.sh": "", "sub/lib.sh": ""})
        self.assertEqual(edges(one), set())
        two = self._model({"a.sh": "source lib.sh\n", "lib.sh": ""})
        self.assertIn(("a.sh", "lib.sh"), edges(two))

    def test_external_tools_and_builtins(self):
        model = self._model({
            "a.sh": "docker ps\naws s3 ls\njq .\n"
                    "echo hi\ngrep foo\ncd /tmp\n"
                    "mine() { :; }\nmine\nother\n",
        })
        self.assertEqual(set(model.externals), {"aws", "docker", "jq", "other"})
        self.assertNotIn("echo", model.externals)
        self.assertNotIn("grep", model.externals)
        self.assertNotIn("cd", model.externals)
        self.assertNotIn("mine", model.externals)

    def test_pipeline_and_subshell_commands(self):
        model = self._model({"a.sh": "echo a | awk '{print}'\nout=$(curl -s url)\n"})
        externals = set(model.externals)
        self.assertIn("curl", externals)
        self.assertNotIn("echo", externals)
        self.assertNotIn("awk", externals)

    def test_exports_and_complexity(self):
        text = """myfn() { :; }
if true; then :; elif false; then :; fi
for x in 1; do :; done
for ((i=0;i<1;i++)); do :; done
while true; do break; done
case x in a) :;; esac
a && b
"""
        tree = langkit.parse("bash", text)
        fx = lang_shell.scan("a.sh", text, tree)
        self.assertEqual(fx.exports, ("myfn",))
        self.assertEqual(fx.complexity, 8)

    def test_shebang_entry_and_library_not(self):
        model = self._model({
            "run.sh": "#!/bin/bash\necho hi\n",
            "lib.sh": "source ./other.sh\n",
        })
        self.assertTrue(model.modules["run.sh"].is_entry)
        self.assertFalse(model.modules["lib.sh"].is_entry)

    def test_bats_load_links_tested_by(self):
        model = self._model({
            "lib/x.sh": "helper() { :; }\n",
            "test/x.bats": 'load ../lib/x\nrun true\n',
        })
        self.assertEqual(model.modules["lib/x.sh"].tested_by, ["test/x.bats"])

    def test_fire_only_on_allowed_extensions(self):
        model = self._model({
            "bad.sh": "if then fi\n",
            "bad.zsh": "#!/bin/zsh\n(( $+functions ))\n",
            "bad.bats": '@test "t" {\n  if then fi\n}\n',
        })
        self.assertTrue(model.modules["bad.sh"].burns)
        self.assertTrue(model.modules["bad.sh"].parse_error)
        self.assertFalse(model.modules["bad.zsh"].burns)
        self.assertTrue(model.modules["bad.zsh"].parse_error)
        self.assertFalse(model.modules["bad.bats"].burns)
        self.assertTrue(model.modules["bad.bats"].parse_error)

    def test_the_sample_town(self):
        model = self._model(lang_shell.SAMPLE)
        self.assertIn(("a.sh", "lib.sh"), edges(model))
        self.assertEqual(model.externals, {"docker": ["a.sh"]})
        self.assertEqual(model.modules["lib.sh"].tested_by, ["test/t.bats"])

    def test_unique_repo_function_gives_road_not_warehouse(self):
        model = self._model({
            "lib.sh": "helper() { echo 1; }\n",
            "a.sh": "helper\n",
        })
        self.assertIn(("a.sh", "lib.sh"), edges(model))
        self.assertNotIn("helper", model.externals)

    def test_ambiguous_repo_function_gives_neither(self):
        model = self._model({
            "a.sh": "fn\n",
            "b.sh": "fn() { :; }\n",
            "c.sh": "fn() { :; }\n",
        })
        self.assertEqual(edges(model), set())
        self.assertNotIn("fn", model.externals)

    def test_standard_utilities_vs_platform_and_service_tools(self):
        model = self._model({
            "a.sh": "tar xf a.tgz\nsudo reboot\npgrep foo\n"
                    "docker ps\ngh pr list\nlaunchctl list\n",
        })
        self.assertEqual(set(model.externals), {"docker", "gh", "launchctl"})
        self.assertNotIn("tar", model.externals)
        self.assertNotIn("sudo", model.externals)
        self.assertNotIn("pgrep", model.externals)

    @needs_grammar("bash")
    def test_functions_in_either_form(self):
        model = survey_files(self, {
            "lib.sh": "f() {\n  if true; then echo; fi\n}\nfunction g {\n  echo\n}\n",
        })
        self.assertEqual(model.modules["lib.sh"].functions, [("f", 3, 2), ("g", 3, 1)])


if __name__ == "__main__":
    unittest.main()
