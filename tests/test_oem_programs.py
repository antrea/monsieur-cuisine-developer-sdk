"""Presets, sub-step cycling, running-knob rules, IPC callbacks, scale display and LED model (STATIC app rules)."""
import math
import unittest

from monsieur_cuisine_sdk import DigitalTwin
from monsieur_cuisine_sdk.profiles.mcc import ipc, led, programs
from monsieur_cuisine_sdk.profiles.mcc.cooking import CookingHost
from monsieur_cuisine_sdk.profiles.mcc.protocol.codec import Operation, decode_frame, encode_tx


def host(**parameters):
    return CookingHost(DigitalTwin('mcc', record=False, parameters=parameters or None))


def latched(h):
    return decode_frame(h.latched)


class PresetData(unittest.TestCase):
    def test_preset_values_match_the_decompiled_app(self):
        knead = programs.kneading_unit()
        self.assertEqual((knead.duration_ms, knead.limit_ms, knead.tag), (45_000, 120_000, 'KNEADING'))
        self.assertEqual([(s.duration_ms, s.configuration) for s in knead.steps], [
            (15_000, programs.MachineConfiguration(5, 4, programs.LEFT, 0)),
            (1_000, programs.MachineConfiguration(5, 0, programs.LEFT, 0)),
            (104_000, programs.MachineConfiguration(5, 4, programs.RIGHT, 0))])
        self.assertTrue(knead.steps[1].rest)
        roast = programs.roasting_unit()
        self.assertEqual((roast.duration_ms, roast.limit_ms), (420_000, 840_000))
        self.assertEqual([s.configuration for s in roast.steps], [
            programs.MachineConfiguration(4, 1, programs.LEFT, 19), programs.MachineConfiguration(4, 0, programs.LEFT, 19)])
        steam = programs.steaming_steps()
        self.assertEqual([(s.duration_ms, s.time_limit_ms, s.preheat) for s in steam.steps],
                         [(600_000, 600_000, True), (1_200_000, 3_600_000, False)])
        self.assertEqual(steam.steps[0].configuration, programs.MachineConfiguration(3, 1, programs.RIGHT, 17))
        self.assertEqual(programs.manual_default().configuration, programs.MachineConfiguration(1, 0, programs.RIGHT, 0))
        with self.assertRaises(ValueError):
            programs.preset('frying')

    def test_kneading_rest_rewrite_and_tick_boundaries(self):
        self.assertEqual(programs.knead_rest_ms(45_000), 1_000)
        self.assertEqual(programs.knead_rest_ms(85_000), 1_000)
        self.assertEqual(programs.knead_rest_ms(100_000), 15_000)
        unit = programs.with_rest(programs.kneading_unit(), 45_000)
        # The app compares with <=, so the rest step is active only at the 16 s tick; at an exact
        # cycle multiple the remainder is 0 and the app selects step 0 again.
        self.assertEqual([programs.active_step_index(unit, t) for t in (0, 15_000, 16_000, 17_000, 119_000, 120_000)],
                         [0, 0, 1, 2, 2, 0])
        self.assertEqual(programs.unit_schedule(programs.kneading_unit(), 45_000), [(0, 0), (16_000, 1), (17_000, 2)])
        self.assertEqual(programs.unit_schedule(programs.kneading_unit(), 100_000), [(0, 0), (16_000, 1), (31_000, 2)])
        # Roasting cycle 35 s: at the 35 s tick the remainder is 0 again (step 0), heating-up from 41 s.
        self.assertEqual(programs.unit_schedule(programs.roasting_unit(), 70_000),
                         [(0, 0), (6_000, 1), (35_000, 0), (41_000, 1), (70_000, 0)])


class HostPrograms(unittest.TestCase):
    def test_kneading_cycle_drives_the_twin_and_rest_keeps_speed_zero(self):
        h = host(); h.start_program('kneading')
        self.assertEqual(h.display_time_ms(), 45_000)
        h.advance(.1)
        frame = latched(h)
        self.assertEqual((frame.operation, frame.speed_level, frame.direction.name), (Operation.KNEAD, 4, 'COUNTER_CLOCKWISE'))
        self.assertEqual(h.twin.get_state().requested_speed, 4)
        h.advance(15.95)  # 16.05 s: rest step latched at the 16 s tick, sent at the next service tick
        self.assertEqual(h.step_index, 1)
        h.advance(.1)
        self.assertEqual(h.twin.get_state().requested_speed, 0)
        self.assertEqual(h.twin.get_state().raw['controller']['extended_state'], 5)
        h.advance(1)   # 17 s tick: right-hand step
        self.assertEqual(h.step_index, 2)
        h.advance(.1)
        self.assertEqual((h.twin.get_state().requested_speed, h.twin.get_state().requested_direction), (4, 'cw'))
        h.advance(28)
        self.assertEqual(h.state, 'FINISHED')
        self.assertEqual(h.twin.get_state().requested_speed, 0)
        names = [e['event'] for e in h.events]
        self.assertEqual(names.count('on_next_step'), 2)
        self.assertIn('on_finish_cooking', names)
        self.assertEqual(h.led.active(h._now_ms()).colour, led.GREEN)

    def test_kneading_locks_knobs_and_limits_time(self):
        h = host(); h.start_program('kneading', seconds=130)
        self.assertEqual(h.display_time_ms(), 120_000)
        with self.assertRaises(ValueError): h.set_speed(3)
        with self.assertRaises(ValueError): h.set_direction('cw')
        with self.assertRaises(ValueError): h.turbo_hold(True)
        h.set_time(100)
        self.assertEqual(h.program.steps[1].duration_ms, 15_000)

    def test_roasting_heated_steps_respect_policy_and_cycle(self):
        h = host(); h.start_program('roasting'); h.advance(.1)
        frame = latched(h)
        self.assertEqual((frame.operation, frame.speed_level, frame.temperature_level), (Operation.TOAST, 1, 19))
        h.advance(6)   # 6 s tick: heating-up sub-step at speed 0 (TOAST may run unstirred)
        self.assertEqual(h.step_index, 1); h.advance(.1)
        self.assertEqual(h.twin.get_state().requested_speed, 0)
        self.assertEqual(h.twin.get_state().raw['controller']['extended_state'], 4)
        h.set_temperature(98)   # temperature knob is the only one roasting leaves editable
        self.assertEqual(h.configuration.temperature_level, 13)

    def test_steaming_sequence_restarts_the_next_step_without_a_green_blink(self):
        h = host(); h.start_program('steaming'); h.advance(.1)
        self.assertEqual(latched(h).operation, Operation.STEAM)
        self.assertEqual(h.display_time_ms(), 599_900)   # running preheat shows its own countdown
        h.set_time(300)                                  # the preheat knob edits the next step
        self.assertEqual(h.program.steps[1].duration_ms, 300_000)
        self.assertEqual(h.display_time_ms(), 599_900)
        h.skip_step()
        self.assertEqual((h.step_index, h.state), (1, 'RUN'))
        self.assertEqual(h.remaining_ms(), 300_000)
        self.assertNotIn('on_finish_cooking', [e['event'] for e in h.events])
        self.assertEqual(h.led.active(h._now_ms()).mode, 'pulse')
        h.advance(300.1)
        self.assertEqual(h.state, 'FINISHED')
        self.assertEqual(h.display_time_ms(), 300_000)   # stopped: the set time of the next step
        with self.assertRaises(ValueError): h.skip_step()

    def test_running_knobs_follow_the_app(self):
        h = host(); h.start(10); h.advance(.1)
        h.set_temperature(60); h.advance(.1)   # heat caps the speed at 3 and re-sends
        self.assertEqual((h.configuration.speed, h.twin.get_state().requested_speed), (3, 3))
        h.set_direction('ccw'); h.advance(.1)
        self.assertEqual(h.twin.get_state().requested_direction, 'ccw')
        h.set_speed(0)
        self.assertEqual(h.state, 'STOP')
        h.start(2); h.twin.set_sensors(temperature=65); h.advance(.1)
        with self.assertRaises(ValueError): h.set_speed(6)
        h.set_speed(6, hot_speed_confirmed=True)
        self.assertEqual(h.configuration.speed, 4)
        h.set_speed(5)   # acknowledged for the session
        self.assertEqual(h.configuration.speed, 5)
        self.assertTrue(h.stirrer_warning)

    def test_time_change_restarts_a_running_countdown_and_zero_stops(self):
        h = host(); h.start(2, seconds=10); h.advance(4)
        h.set_time(10)                                   # unchanged value: the app keeps the timer
        self.assertEqual(h.remaining_ms(), 6_000)
        h.set_time(12)                                   # new value: elapsed restarts from zero
        self.assertEqual(h.remaining_ms(), 12_000)
        h.set_time(0)
        self.assertEqual(h.state, 'STOP')
        countup = host(); countup.start(2); countup.advance(4); countup.set_time(5)
        self.assertEqual(countup.elapsed_ms(), 4_000)
        self.assertFalse(countup.countdown)

    def test_strict_policy_refuses_adjusted_program_steps(self):
        h = host(host_policy='strict')
        with self.assertRaises(ValueError):
            h.start(0)   # STANDARD at speed 0 would be raised to 1
        h.start_program('roasting')   # TOAST at speed 0/1 needs no adjustment
        self.assertEqual(h.state, 'RUN')


class IpcCallbacks(unittest.TestCase):
    def frame(self, **sensors):
        twin = DigitalTwin('mcc', record=False)
        if sensors:
            twin.set_sensors(**sensors)
        return decode_frame(twin.sample()[0])

    def test_snapshot_mapping_and_defaults(self):
        snapshot = ipc.IpcSnapshot.from_frame(self.frame(weight=123, temperature=40, lid_open=True, error_code=6))
        self.assertEqual((snapshot.weight, snapshot.temperature, snapshot.lid, snapshot.error), (123, 40, ipc.LID_OPEN, 5))
        self.assertEqual(ipc.DEFAULT_SNAPSHOT.lid, ipc.LID_CLOSED)
        self.assertEqual(ipc.IpcSnapshot.from_frame(self.frame()).direction, 1)

    def test_change_callbacks_and_edge_triggered_bad_state(self):
        base = ipc.IpcSnapshot()
        hot = ipc.IpcSnapshot(temperature=50)
        self.assertEqual(ipc.callbacks(base, hot), [("on_temperature_changed", 50)])
        error = ipc.IpcSnapshot(temperature=50, error=4)
        self.assertEqual(ipc.callbacks(hot, error), [("on_bad_state", [4])])
        self.assertEqual(ipc.callbacks(error, error), [])          # a persisting error is reported once
        self.assertEqual(ipc.callbacks(error, hot), [])            # clearing raises nothing
        overload = ipc.IpcSnapshot(temperature=50, error=4, scale_state=ipc.SCALE_OVERLOAD)
        self.assertEqual(ipc.callbacks(error, overload),
                         [("on_scale_state_changed", 1, 0, 0), ("on_bad_state", [7, 4])])
        lid = ipc.IpcSnapshot(lid=ipc.LID_OPEN)
        self.assertEqual(ipc.callbacks(base, lid), [("on_lid_opened",)])
        self.assertEqual(ipc.callbacks(lid, base), [("on_lid_closed",)])
        self.assertEqual(ipc.collect_warnings(ipc.IpcSnapshot(scale_state=ipc.SCALE_OVERLOAD)), [7])
        self.assertEqual(ipc.visible_warnings([7, 4]), [4])
        self.assertEqual(ipc.visible_warnings([7, 4], scale_view_visible=True), [7, 4])

    def test_host_raises_callbacks_and_dialog_on_error_edge(self):
        h = host(); h.start(2); h.advance(.2)
        self.assertIn('on_motor_state_changed', [e['event'] for e in h.events])
        h.twin.set_sensors(error_code=3); h.advance(.3)
        dialogs = [e for e in h.events if e['event'] == 'dialog']
        self.assertEqual([d['codes'] for d in dialogs], [[2]])
        self.assertEqual(h.state, 'RUN')              # app keeps running for this code
        self.assertEqual(h.led.active(h._now_ms()).colour, led.RED)
        h.advance(3)
        self.assertEqual(h.led.active(h._now_ms()).mode, 'solid')


class ScaleDisplay(unittest.TestCase):
    def test_rounding_matches_java_math_round(self):
        self.assertEqual([ipc.rounded_weight(g) for g in (0, 2, 3, 12, 13, -12, -13, 4997)],
                         [0, 0, 5, 10, 15, -10, -15, 4995])
        self.assertEqual(ipc.weight_text(13), '15g')
        self.assertEqual(ipc.weight_text(13, overload=True), '----g')


class LedBehaviour(unittest.TestCase):
    def test_pulse_blink_timeout_and_off(self):
        model = led.LedModel()
        model.solid(0, led.WHITE)
        self.assertEqual(model.rgb_at(10), (0, 0, 50))
        model.pulse(100, led.WHITE)
        self.assertEqual(model.rgb_at(100), (0, 0, int(50 * led.PULSE_CURVE[1])))
        self.assertEqual(model.rgb_at(100 + 49 * 30), (0, 0, 0))     # curve index 50 is the trough
        self.assertEqual(model.rgb_at(100 + 99 * 30), (0, 0, 50))    # index 0 is the peak
        model.blink(1000, led.GREEN, timeout_ms=3000)
        self.assertEqual(model.rgb_at(1000), led.GREEN)
        self.assertEqual(model.rgb_at(1500), led.OFF)
        self.assertEqual(model.rgb_at(2000), led.GREEN)
        self.assertEqual(model.rgb_at(4000), led.WHITE)               # timeout reverts to solid white
        model.off(5000)
        self.assertTrue(model.is_off(5000))
        with self.assertRaises(ValueError): model.request(4000, 'solid', led.WHITE)
        with self.assertRaises(ValueError): model.request(6000, 'strobe', led.WHITE)

    def test_host_led_follows_session_state(self):
        h = host()
        self.assertEqual(h.led_rgb(), led.WHITE)
        h.start(2); self.assertEqual(h.led.active(h._now_ms()).mode, 'pulse')
        h.pause(); self.assertEqual(h.led_rgb(), led.WHITE)
        h.advance(450); h.advance(.1)
        self.assertEqual(h.state, 'STOP')     # pause auto-stop, then idle
        h.advance(450)
        self.assertEqual(h.state, 'SLEEP')
        self.assertTrue(h.led.is_off(h._now_ms()))
        h.wake(); self.assertEqual(h.led_rgb(), led.WHITE)


if __name__ == '__main__':
    unittest.main()
