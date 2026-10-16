# Scenarios and stress

The common scenario runner creates a fresh selected-profile twin, supplies explicit virtual time and verifies its resulting recording. It opens no socket, GUI or device. The result contains `PASS`, `model`, `name`, `seed`, `checks`, `final_state` and `recording`.

```sh
mc-sdk --model mcc scenario start_stop
mc-sdk --model mcs simulate thermal
mc-sdk --model mcc stress --count 1000 --seed 292
```

```python
from monsieur_cuisine_sdk.scenarios import run_scenario, run_stress

assert run_scenario("mcc", "start_stop")["PASS"]
assert run_scenario("mcs", "thermal")["PASS"]
assert run_stress("mcs", count=20, seed=292)["PASS"]
```

Available names: `start_stop`, `directions`, `reversal`, `intermittent`, `wait_stop`, `partial_corrupt`, `stale`, `disconnect`, `response_loss`, `lid`, `error`, `stop_phases`, `late_timer`, `interrupted`, `thermal`, `link_faults`.

Names are shared entrypoints, not a claim that all firmware semantics are equivalent. The common application requests STOP after injected lid/error events rather than inventing a shared MCU interlock. Some named checks reuse a bounded start/stop or corruption exercise; inspect `checks` to see exactly what ran. The canonical MCC intermittent state machine and MCS independent scenario engine retain richer profile-specific historical checks in the device archive.

The current shared checks include concrete lifecycle/timer cases:

| Scenario | What is exercised |
|---|---|
| `wait_stop` | Two start/STOP cycles with virtual-time observation of eventual zero before the next cycle |
| `stale` | An incomplete command, disarm boundary and old tail cannot actuate; after clearing any ambiguous stale remainder at a fresh transport boundary, a complete valid command works |
| `stop_phases` | STOP while idle, accelerating, cruising, braking, reversing, lid-open and in error; each phase checks target removal, eventual zero and no restart |
| `late_timer` on MCS | Native one-second timer expiry plus STOP before a later deadline; late time cannot restart motion |
| `late_timer` on MCC | Nonzero wire duration is rejected explicitly, then a normal STOP remains stopped after late virtual time |

These checks describe the implemented software expectations and preserve the devices' different timer support. They do not add a common timer opcode or infer physical stopping time.

`run_stress` accepts 1–10000 distinct seeded cases. Each case chooses 24 actions plus 24 advances, reports failures by case, and disarms at the end. Repeating seed/model/count repeats software inputs. This is synthetic regression testing, not a real-time load test, motor duty-cycle recommendation or physical safety test. Optional cancellation belongs to the owning application; long GUI work should not block its event loop.
