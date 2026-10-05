import unittest

from events import Agent, Event


class EventsTest(unittest.TestCase):
    def test_agent_and_event_fields(self):
        agent = Agent("w2-world/task-1", "implementer", "world", "w2-world")
        event = Event("edit", agent, "tools/x.py", seen=42.0)
        self.assertEqual(event.kind, "edit")
        self.assertEqual(event.agent.id, "w2-world/task-1")
        self.assertEqual(event.path, "tools/x.py")
        self.assertEqual(event.seen, 42.0)

    def test_events_are_frozen(self):
        event = Event("merge", None)
        with self.assertRaises(AttributeError):
            event.kind = "edit"


if __name__ == "__main__":
    unittest.main()
