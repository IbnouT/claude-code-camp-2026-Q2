"""The step's headline evidence: what caching does, and does not, change.

Caching is the whole lever of this step, so this is the only check that shows it
worked, and it runs automatically rather than depending on someone playing. It
sends the same prompt twice against the configured provider, cold then warm.

Every expectation is derived from what the backend DECLARES, never from a branch
on a provider or model name. The five providers differ enough that a test written
against one is wrong on the others:

- one assertion holds everywhere: volume processed is unchanged between the two
  runs, which is the invariance the corrected token ceiling depends on, and it is
  true even where nothing is cached at all;
- cache reads are asserted only where the backend caches AND the prompt exceeds
  that model's own minimum, read from the catalog;
- a cost fall is asserted only where the rate table covers the classes in play,
  and where it does not, that cost reports unavailable rather than a number.

Gated on the provider key. Without it the test skips with a notice, so a keyless
suite stays green.
"""

import os
import unittest
import uuid

from boukensha.config import Config
from boukensha.backends import backend_for
from boukensha.context import Context
from boukensha.message import Message
from boukensha.client import Client
from boukensha.prompt_builder import PromptBuilder
from boukensha.tasks import Player
from boukensha.usage import normalize

#: Long enough to clear a large per-model minimum, since a short prompt is not
#: cached and no error is returned. Built from repeated sentences rather than one
#: huge token so it looks like real prose to any tokenizer.
FILLER = ("The labyrinth beneath the city has many rooms, and each room has "
          "exits leading to further rooms. ") * 400


def _unique_prefix() -> str:
    """A prompt no earlier run has sent, so the first call is genuinely cold.

    A provider's cache outlives a test run: a five-minute entry from a run two
    minutes ago makes the next run's "cold" call a cache hit, and the comparison
    then measures nothing. Varying the prefix per run is what makes cold mean
    cold. It costs one cache write per run, which is the price of the test being
    honest.
    """
    return f"Session {uuid.uuid4()}. You are exploring a labyrinth.\n" + FILLER


def _live_backend():
    """The configured provider, or None with a reason to skip.

    Config is built first because it loads ``.boukensha/.env``, which is where the
    gate and the key may live. Reading the raw environment first would skip a run
    the operator had in fact opted into.
    """
    config = Config()
    if os.environ.get("BOUKENSHA_LIVE") != "1":
        return None, "BOUKENSHA_LIVE is not 1"
    settings = config.tasks(Player.task_name)
    provider, model = Player.provider(settings), Player.model(settings)
    backend = backend_for(provider, model)
    if backend.api_key_env and not os.environ.get(backend.api_key_env):
        return None, f"{backend.api_key_env} is not set"
    return backend, f"{provider}/{model}"


class TestColdVersusWarm(unittest.TestCase):
    def test_caching_changes_price_and_not_work(self):
        backend, why = _live_backend()
        if backend is None:
            self.skipTest(f"live run skipped: {why}")

        context = Context(_unique_prefix())
        context.add(Message.user("Name one room you might find. Answer in a word."))
        builder = PromptBuilder(context, backend, ())
        client = Client(builder)

        cold = normalize(client.call(max_output_tokens=16))
        warm = normalize(client.call(max_output_tokens=16))

        # (1) True on every provider, cached or not: the same prompt is the same
        # work SENT. Caching redistributes it between fresh and cached, and the
        # total does not move. This is what lets a volume ceiling keep its
        # meaning when caching is switched on.
        #
        # Asserted on the prompt rather than on prompt-plus-output deliberately.
        # Output is GENERATED, not sent, and a live model does not produce the
        # same number of tokens twice, so including it would test the model's
        # determinism instead of the property under test. Narrowing it here is
        # making the assertion exact, not loosening it: the cached and fresh
        # counts below still have to add up to this same total.
        self.assertEqual(cold.prompt_tokens, warm.prompt_tokens,
                         f"the prompt changed size between identical calls on {why}")
        self.assertEqual(cold.prompt_tokens,
                         warm.fresh_input + warm.cache_read + warm.cache_write,
                         "the warm call's classes do not add up to the same prompt")

        prompt_tokens = warm.prompt_tokens
        minimum = backend.cache_min_tokens
        status = backend.cache_status(prompt_tokens)

        # (2) Cache reads, only where this backend and this model can cache.
        if backend.caches and prompt_tokens >= (minimum or 0):
            self.assertGreater(
                warm.cache_read, 0,
                f"{why} declares caching and the prompt ({prompt_tokens}) clears "
                f"its {minimum} minimum, but the warm call read nothing from cache")
        else:
            self.assertEqual("on" if backend.caches else status, status)

        # (3) Cost falls, only where the rates cover what was used. The cold call
        # pays a write premium and the warm call a read discount, which is the
        # trade caching makes: pay a little more once, far less thereafter.
        cold_cost, warm_cost = backend.cost_of(cold), backend.cost_of(warm)
        if not cold_cost.available:
            self.assertFalse(warm_cost.available,
                             "an unpriced model must report unavailable, not a number")
        elif warm.cache_read and not warm_cost.unpriced:
            self.assertLess(warm_cost.total, cold_cost.total,
                            f"{why} served {warm.cache_read} cached tokens yet cost "
                            f"no less")

        print(f"\n  {why}: caching {status}")
        print(f"  cold  fresh={cold.fresh_input} read={cold.cache_read} "
              f"volume={cold.volume} cost={cold_cost.render()}")
        print(f"  warm  fresh={warm.fresh_input} read={warm.cache_read} "
              f"volume={warm.volume} cost={warm_cost.render()}")


if __name__ == "__main__":
    unittest.main()
