"""Run: python -m unittest discover -s tests -v   (no pytest, no network, no GPU)"""

import dataclasses
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import (DialogueManager, DialogueState, DMResult, EndCall, HandOff,
                               step)
from voxstage.events import EventLog, read_events
from voxstage.turn import ButtonPress, Dtmf, Utterance, describe


class CounterDM(DialogueManager):
    """Test double: remembers the last input kind in state, hands off on button 'agent'."""

    name = "counter"

    def respond(self, state, turn_input):
        match turn_input:
            case Utterance(text=text):
                return DMResult(f"heard:{text}", state.evolve(slots={**state.slots, "last": text}),
                                trace={"rule": "echo"})
            case Dtmf(digits=digits):
                return DMResult(f"digits:{digits}", state.evolve(slots={**state.slots, "pin": digits}))
            case ButtonPress(button_id="agent"):
                return DMResult("connecting", state, actions=(HandOff("user_pressed_agent"),))
            case ButtonPress(button_id="bye"):
                return DMResult("bye", state, actions=(EndCall(),))
            case _:
                return DMResult("?", state)


class TurnInputTest(unittest.TestCase):
    def test_describe_each_kind(self):
        self.assertEqual(describe(Utterance("안녕", confidence=0.9))["kind"], "utterance")
        self.assertEqual(describe(Dtmf("1234")), {"kind": "dtmf", "digits": "1234"})
        self.assertEqual(describe(ButtonPress("ok", "2"))["value"], "2")

    def test_unknown_input_is_rejected(self):
        with self.assertRaises(TypeError):
            describe("raw string")

    def test_inputs_are_immutable(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            Dtmf("1").digits = "2"


class StepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "events.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_step_does_not_mutate_previous_state(self):
        dm = CounterDM()
        s0 = dm.initial_state("s1")
        r1 = step(dm, s0, Utterance("a"))
        self.assertEqual(s0.slots, {})
        self.assertEqual(s0.turn, 0)
        self.assertEqual(r1.state.slots, {"last": "a"})
        self.assertEqual(r1.state.turn, 1)

    def test_replay_from_inputs_is_deterministic(self):
        dm = CounterDM()
        inputs = [Utterance("a"), Dtmf("12"), ButtonPress("ok")]

        def run():
            state, replies = dm.initial_state("s1"), []
            for i in inputs:
                r = step(dm, state, i)
                state = r.state
                replies.append(r.reply)
            return replies, state.slots

        self.assertEqual(run(), run())

    def test_events_recorded_for_each_input_kind(self):
        log = EventLog(self.path)
        dm = CounterDM()
        state = dm.initial_state("s1")
        for i in (Utterance("hi"), Dtmf("99"), ButtonPress("agent")):
            r = step(dm, state, i, log=log)
            state = r.state
        log.close()
        rows = read_events(self.path)
        kinds = [r["data"]["kind"] for r in rows if r["type"] == "input"]
        self.assertEqual(kinds, ["utterance", "dtmf", "button"])
        last = [r for r in rows if r["type"] == "dm_response"][-1]
        self.assertEqual(last["data"]["actions"], ["HandOff"])
        self.assertEqual([r["turn"] for r in rows if r["type"] == "input"], [0, 1, 2])

    def test_unknown_input_fails_before_dm_runs(self):
        dm = CounterDM()
        with self.assertRaises(TypeError):
            step(dm, dm.initial_state("s1"), "raw")

    def test_state_is_frozen(self):
        s = DialogueState(session_id="s1")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            s.turn = 5


if __name__ == "__main__":
    unittest.main()
