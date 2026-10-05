import os
import unittest

import langkit
import lang_ruby
import problems as prob
from langtest import edges, needs_grammar, survey_files
from layers import Rows
from model import Module


def scan(text, path="x.rb"):
    tree = langkit.parse("ruby", text)
    return lang_ruby.scan(path, text, tree)


@needs_grammar("ruby")
class RubyAdapterTest(unittest.TestCase):
    def test_require_relative(self):
        model = survey_files(self, {
            "lib/a.rb": "require_relative \"b\"\n",
            "lib/b.rb": "class B; end\n",
        })
        self.assertIn(("lib/a.rb", "lib/b.rb"), edges(model))

    def test_require_reaches_lib_path(self):
        model = survey_files(self, {
            "lib/acme/parser.rb": "class Parser; end\n",
            "app/run.rb": "require \"acme/parser\"\n",
        })
        self.assertIn(("app/run.rb", "lib/acme/parser.rb"), edges(model))

    def test_stdlib_and_gem_warehouses(self):
        model = survey_files(self, {
            "lib/x.rb": "require \"json\"\nrequire \"httparty\"\nrequire \"active_support/core_ext\"\n",
            "Gemfile": "gem \"httparty\"\ngem \"activesupport\"\n",
        })
        self.assertNotIn("json", model.externals)
        self.assertEqual(model.externals.get("httparty"), ["lib/x.rb"])
        self.assertEqual(model.externals.get("activesupport"), ["lib/x.rb"])

    def test_reference_without_autoload_has_no_road(self):
        model = survey_files(self, {
            "app/models/user.rb": "class User; end\n",
            "app/run.rb": "User\n",
        })
        self.assertEqual(edges(model), set())

    def test_autoload_controller_reaches_model(self):
        model = survey_files(self, {
            "Gemfile": "gem \"rails\"\n",
            "app/models/user.rb": "class User; end\n",
            "app/controllers/users_controller.rb": "class UsersController; User; end\n",
        })
        self.assertIn(("app/controllers/users_controller.rb", "app/models/user.rb"), edges(model))

    def test_reference_nesting(self):
        model = survey_files(self, {
            "Gemfile": "gem \"zeitwerk\"\n",
            "app/models/admin/report.rb": "module Admin; class Report; end; end\n",
            "app/models/report.rb": "class Report; end\n",
            "app/run.rb": "module Admin\nReport\nend\n",
        })
        self.assertIn(("app/run.rb", "app/models/admin/report.rb"), edges(model))
        model2 = survey_files(self, {
            "Gemfile": "gem \"zeitwerk\"\n",
            "app/models/report.rb": "class Report; end\n",
            "app/run.rb": "module Admin\nReport\nend\n",
        })
        self.assertIn(("app/run.rb", "app/models/report.rb"), edges(model2))

    def test_zeitwerk_file_rule(self):
        model = survey_files(self, {
            "Gemfile": "gem \"rails\"\n",
            "app/mailers/billing/invoice_mailer.rb": "class Billing::InvoiceMailer; end\n",
            "app/run.rb": "Billing::InvoiceMailer\n",
        })
        self.assertIn(("app/run.rb", "app/mailers/billing/invoice_mailer.rb"), edges(model))

    def test_exports(self):
        fx = scan("""class X
  def pub; end
  private
  def hidden; end
  private def secret; end
  attr_reader :name
end
""")
        self.assertEqual(set(fx.exports), {"pub", "name"})

    def test_complexity(self):
        text = """
if x; end
unless x; end
while x; end
until x; end
for i in a; end
case x; when 1; end
begin; rescue; end
a ? b : c
x && y
x || y
x and y
x or y
1 if true
1 unless false
x while true
y until false
1 rescue nil
"""
        self.assertEqual(scan(text).complexity, 18)

    def test_entry_points(self):
        self.assertTrue(scan("#!/usr/bin/env ruby\n", "bin/setup").is_entry)
        self.assertTrue(scan("class T; end\n", "exe/tool.rb").is_entry)
        self.assertTrue(scan("task :x do; end\n", "lib/tasks/x.rake").is_entry)

    def test_rails_public_and_abandoned(self):
        model = survey_files(self, {
            "Gemfile": "gem \"rails\"\n",
            "app/controllers/home_controller.rb": "class HomeController; end\n",
            "app/models/orphan.rb": "class Orphan; end\n",
        })
        kinds = {m.id: [p.kind for p in prob.find(model, Rows()) if p.module == m.id]
                 for m in model.modules.values()}
        self.assertNotIn(prob.ABANDONED, kinds["app/controllers/home_controller.rb"])
        self.assertIn(prob.ABANDONED, kinds["app/models/orphan.rb"])

    def test_spec_reference_links_tested_by(self):
        model = survey_files(self, {
            "Gemfile": "gem \"rails\"\n",
            "app/models/user.rb": "class User; end\n",
            "spec/models/user_spec.rb": "User\n",
        })
        self.assertIn("spec/models/user_spec.rb", model.modules["app/models/user.rb"].tested_by)

    def test_schema_excluded(self):
        model = survey_files(self, {
            "db/schema.rb": "ActiveRecord::Schema.define do; end\n",
            "lib/x.rb": "class X; end\n",
        })
        self.assertNotIn("db/schema.rb", model.modules)

    def test_syntax_error_is_fire(self):
        model = survey_files(self, {
            "lib/broken.rb": "class X\n  def (\nend\n",
        })
        fires = [p for p in prob.find(model, Rows()) if p.kind == prob.FIRE]
        self.assertEqual(len(fires), 1)
        self.assertEqual(fires[0].module, "lib/broken.rb")

    def test_rails_autoload_one_arg_nesting(self):
        model = survey_files(self, {
            "lib/action_cable/server/worker.rb": "class Worker; end\n",
            "lib/action_cable.rb": "module ActionCable\n  module Server\n    autoload :Worker\n  end\nend\n",
        })
        self.assertIn(("lib/action_cable.rb", "lib/action_cable/server/worker.rb"), edges(model))

    def test_rails_eager_autoload(self):
        model = survey_files(self, {
            "lib/active_record/base.rb": "class Base; end\n",
            "lib/active_record.rb": "module ActiveRecord\n  eager_autoload do\n    autoload :Base\n  end\nend\n",
        })
        self.assertIn(("lib/active_record.rb", "lib/active_record/base.rb"), edges(model))

    def test_rails_autoload_under(self):
        model = survey_files(self, {
            "lib/active_record/relation/predicate.rb": "class Predicate; end\n",
            "lib/active_record.rb": "module ActiveRecord\n  autoload_under \"relation\" do\n    autoload :Predicate\n  end\nend\n",
        })
        self.assertIn(("lib/active_record.rb", "lib/active_record/relation/predicate.rb"), edges(model))

    def test_rails_autoload_at(self):
        model = survey_files(self, {
            "lib/action_view/buffers.rb": "class OutputBuffer; class StreamingBuffer; end\n",
            "lib/action_view.rb": "module ActionView\n  autoload_at \"action_view/buffers\" do\n    autoload :OutputBuffer\n    autoload :StreamingBuffer\n  end\nend\n",
        })
        self.assertIn(("lib/action_view.rb", "lib/action_view/buffers.rb"), edges(model))
        fx = scan("module ActionView\n  autoload_at \"action_view/buffers\" do\n    autoload :OutputBuffer\n    autoload :StreamingBuffer\n  end\nend\n", "lib/action_view.rb")
        specs = [i.spec for i in fx.imports if i.kind == "import"]
        self.assertEqual(specs, ["action_view/buffers", "action_view/buffers"])

    def test_rails_autoload_underscore(self):
        model = survey_files(self, {
            "lib/action_dispatch/params_wrapper.rb": "class ParamsWrapper; end\n",
            "lib/action_dispatch.rb": "module ActionDispatch\n  autoload :ParamsWrapper\nend\n",
        })
        self.assertIn(("lib/action_dispatch.rb", "lib/action_dispatch/params_wrapper.rb"), edges(model))

    @needs_grammar("ruby")
    def test_functions_are_instance_and_class_methods(self):
        model = survey_files(self, {
            "lib/a.rb": "class A\n  def f(x)\n    if x && y\n      1\n    end\n  end\n\n"
                        "  def self.g\n  end\nend\n\ndef top; end\n",
        })
        self.assertEqual(model.modules["lib/a.rb"].functions,
                         [("f", 5, 3), ("g", 2, 1), ("top", 1, 1)])


if __name__ == "__main__":
    unittest.main()
