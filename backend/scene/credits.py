"""Credits: what a generation costs, and charging and refunding users.

The price is what the customer asked for, never the GPU time it took: an image costs a flat amount, and a video,
a sound, a motion graphic, a title laid over a video or an upscale costs an amount per second of the result. An admin sets the rates in the
admin console (Pricing), for each kind and, where one needs its own, for a single workflow.

What was chosen changes the price too: a resolution and a quality each multiply it (FACTORS), so a 480p draft costs
less than a 1080p final. The factors are the studio's, set in the console, and a workflow may have its own.

A job is charged when it is queued and refunded if it fails or is cancelled.
"""

import contextvars
import math
import json
import time

from fastapi import HTTPException

# The rates a new installation starts with. Per generation for the kinds in PER_JOB, per second for the rest.
RATES = {"image": 40, "video": 20, "audio": 5, "motion": 30, "overlay": 10, "upscaler": 20}
PER_JOB = ("image",)
MOTION = "edit/motion"       # what a motion graphic is priced and filed under; it has no workflow file
OVERLAY = "edit/overlay"     # what a motion graphic laid over a video the user has is priced under
ASSUMED_SECONDS = 5          # billed when a per-second workflow does not say how long its result is
# How much each resolution and quality multiplies the price, to begin with. 720p and final cost the rate itself; 768p (the
# short edge MiniMax H3 renders at) is priced as 720p. Quality is "draft"/"final" for most workflows and
# "low"/"medium"/"high" for some video ones. A picture is priced by its quality only, not its size.
FACTORS = {"resolution": {"480": 0.6, "720": 1.0, "1080": 2.0},
           "quality": {"draft": 0.5, "final": 1.0, "low": 0.6, "medium": 0.8, "high": 1.0}}
RESOLUTION_TIER = {480: "480", 720: "720", 768: "720", 1080: "1080"}
TIERS = ("480", "720", "1080")
# Resolutions an admin switched off (the console's Workflows section), in the setting "resolutions_off":
# {"video": ["1080"], "video/h3_all_in_one": ["480"]}. A kind's list holds for each of its workflows, a workflow's adds to it.
RESOLUTIONS_OFF = "resolutions_off"
INR_PER_1000_CREDITS = 100
ELECTRICITY_INR_PER_KWH = 8
# What Anthropic charges for a Claude model, in US dollars per million tokens: (input, output, cache read, cache write).
# Claude Code writes its cache for an hour, at twice the input price. The first key in the model's name wins, so the
# older models come before the names Claude Code gives the current ones ("claude/opus" is Opus 5.5). Prices of 30 October
# 2026; Haiku 5.5's are for prompts up to 100K tokens, and its cache prices are 0.1× and 2× its input, as for the others.
CLAUDE_PRICES = (("fable", (10, 50, 0.25, 20)), ("mythos", (10, 50, 0.25, 20)),
                 ("opus-4", (5, 25, 0.50, 10)), ("opus-5-5", (4, 20, 0.20, 8)), ("opus-5", (5, 25, 0.50, 10)), ("opus", (4, 20, 0.20, 8)),
                 ("sonnet-4", (3, 15, 0.30, 6)), ("sonnet", (2, 10, 0.20, 4)),
                 ("haiku-4", (1, 5, 0.10, 2)), ("haiku", (0.10, 0.50, 0.01, 0.20)))
INR_PER_USD = 88


def _number(value):
    try:
        return float(value) >= 0
    except (TypeError, ValueError):
        return False


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def kind_of(workflow_id):
    return {MOTION: "motion", OVERLAY: "overlay"}.get(workflow_id) or workflow_id.split("/", 1)[0]


# The plan whose reservation pays for what is charged now: set by the plan runner while it queues a step (plans.py).
PREPAID = contextvars.ContextVar("prepaid", default=None)


class OverCap(HTTPException):
    """A charge that would take the user past their daily limit (Credits.charge): a 429, its detail cap_problem's words."""

    def __init__(self, detail):
        super().__init__(429, detail)


class Credits:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    @property
    def signup(self):
        return int(float(self.db.setting("signup_credits", self.settings.signup_credits)))

    @property
    def inr_per_1000(self):
        return float(self.db.setting("inr_per_1000_credits", INR_PER_1000_CREDITS))

    @property
    def electricity_rate(self):
        return float(self.db.setting("electricity_inr_per_kwh", ELECTRICITY_INR_PER_KWH))

    def rates(self):
        return {kind: float(self.db.setting("rate_" + kind, default)) for kind, default in RATES.items()}

    def llm_prices(self):
        """What a message to the agent costs, by model: {"claude/opus": 2}. A model not listed is free."""
        try:
            found = json.loads(self.db.setting("llm_prices", "{}") or "{}")
        except ValueError:
            found = {}
        return {str(k): int(v) for k, v in found.items() if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0}

    def set_llm_price(self, model, credits):
        prices = self.llm_prices()
        if credits:
            prices[model] = int(credits)
        else:
            prices.pop(model, None)
        self.db.set_setting("llm_prices", json.dumps(prices))

    def llm_cost(self, model):
        return self.llm_prices().get(str(model or ""), 0)

    @property
    def inr_per_usd(self):
        return float(self.db.setting("inr_per_usd", INR_PER_USD))

    @staticmethod
    def token_prices(model):
        """Anthropic's prices for a Claude model ("claude/opus", "claude/claude-sonnet-5-5"), as in CLAUDE_PRICES, or None
        for a model that is not Claude's."""
        name = str(model or "").lower()
        if not name.startswith("claude/"):
            return None
        return next((prices for key, prices in CLAUDE_PRICES if key in name), None)

    def token_cost(self, model, tokens):
        """Credits for the tokens one answer of a Claude model used ({"prompt", "cached", "written", "answer"}, as
        claude.judged counts them): what Anthropic charges for them, in rupees, at what a credit is worth. 0 for a model
        that is not priced by its tokens. A flat price per message (llm_prices) is set over this, not added to it."""
        prices = self.token_prices(model)
        if not prices or not tokens or self.inr_per_1000 <= 0:
            return 0
        count = lambda key: max(0, int(tokens.get(key) or 0))
        read, written = count("cached"), count("written")
        fresh = max(0, count("prompt") - read - written)
        usd = (fresh * prices[0] + count("answer") * prices[1] + read * prices[2] + written * prices[3]) / 1e6
        return math.ceil(round(usd * self.inr_per_usd * 1000 / self.inr_per_1000, 6))

    def message_cost(self, model, tokens):
        """What one answer of the agent costs: the model's flat price per message when an admin set one, else its tokens."""
        return self.llm_cost(model) or self.token_cost(model, tokens)

    def pricing(self, workflow_id):
        """The workflow's own pricing, or None when it follows the rate of its kind. Kept in the shared cache with several
        processes (shared.py), dropped when a price changes (pricing_changed)."""
        read = lambda: self.db.one("SELECT * FROM workflow_pricing WHERE workflow = ?", (workflow_id,))   # noqa: E731
        return self.db.shared.cached("pricing", workflow_id, read) if self.db.shared is not None else read()

    def pricing_changed(self):
        """A workflow's price or audience changed: every process reads it again."""
        if self.db.shared is not None:
            self.db.shared.changed("pricing")

    def enabled(self, workflow_id, user=None):
        """Whether `user` may use the workflow: it is switched on and, while it is tried out by admins alone (the
        console's Workflows section), they are one. With no user, as for anyone who is not an admin."""
        row = self.pricing(workflow_id)
        if not row:
            return True
        return bool(row["enabled"]) and (not row["admins_only"] or bool(user and user.get("role") == "admin"))

    def rate_for(self, workflow_id):
        """(base credits, credits per second, multiplier) for one workflow."""
        kind = kind_of(workflow_id)
        rate = self.rates().get(kind, 0)
        base, per_second = (rate, 0) if kind in PER_JOB else (0, rate)
        row = self.pricing(workflow_id) or {}
        if row.get("base_credits") is not None:
            base = row["base_credits"]
        if row.get("credits_per_second") is not None:
            per_second = row["credits_per_second"]
        return base, per_second, row.get("resolution_multiplier", 1) * row.get("quality_multiplier", 1)

    def cost(self, workflow_id, seconds=None, chosen=None):
        """Credits for one job. `seconds` is the length of the result that was asked for, when it has one; `chosen`, what
        was picked (the job's context: its resolution and quality), which multiplies the price (factors)."""
        base, per_second, multiplier = self.rate_for(workflow_id)
        seconds = ASSUMED_SECONDS if seconds is None else seconds
        return math.ceil(round((base + per_second * seconds) * multiplier * self.choice_factor(workflow_id, chosen), 6))

    def factors(self, workflow_id=None):
        """The resolution and quality factors in force: the studio's (setting price_factors, over FACTORS), and over them
        a workflow's own, when it has some (workflow_pricing.factors)."""
        found = {group: dict(values) for group, values in FACTORS.items()}
        for layer in (self._json(self.db.setting("price_factors", "") or "{}"),
                      self._json((self.pricing(workflow_id) or {}).get("factors") or "{}") if workflow_id else {}):
            for group in found:
                found[group].update({str(k): float(v) for k, v in (layer.get(group) or {}).items() if _number(v)})
        return found

    def choice_factor(self, workflow_id, chosen):
        """What the chosen resolution and quality multiply a workflow's price by (1 for what has no factor)."""
        if not chosen:
            return 1.0
        found, factor = self.factors(workflow_id), 1.0
        tier = RESOLUTION_TIER.get(_int(chosen.get("resolution")))
        if tier and kind_of(workflow_id) not in PER_JOB:   # a picture is priced by its quality, not its size
            factor *= found["resolution"].get(tier, 1.0)
        if chosen.get("quality") is not None:
            factor *= found["quality"].get(str(chosen["quality"]), 1.0)
        return factor

    # ------------------------------------------------------------ resolutions switched off

    def resolutions_off(self):
        """Every switch: {kind or workflow id: ["1080", ...]}, the tiers in TIERS order."""
        found = self._json(self.db.setting(RESOLUTIONS_OFF, "") or "{}")
        return {str(key): [t for t in TIERS if t in {str(v) for v in values}]
                for key, values in found.items() if isinstance(values, list) and any(str(v) in TIERS for v in values)}

    def set_resolutions_off(self, key, tiers):
        """Switch off these tiers ("480", "720", "1080") for a kind or one workflow; an empty list switches them all on."""
        switches = self.resolutions_off()
        tiers = [t for t in TIERS if t in {str(v) for v in tiers or []}]
        if tiers:
            switches[str(key)] = tiers
        else:
            switches.pop(str(key), None)
        self.db.set_setting(RESOLUTIONS_OFF, json.dumps(switches))
        return tiers

    def tiers_off(self, workflow_id):
        """The tiers switched off for a workflow: its kind's and its own."""
        switches = self.resolutions_off()
        return set(switches.get(kind_of(workflow_id), [])) | set(switches.get(workflow_id, []))

    def allowed_resolutions(self, workflow_id, offered=(480, 720, 768, 1080)):
        """The resolutions of `offered` (a workflow's, as workflows.describe lists them) that are not switched off. What
        the agent may choose from; a job asked at another one is made at the next one allowed (fit_resolution)."""
        off = self.tiers_off(workflow_id)
        return [r for r in offered if RESOLUTION_TIER.get(_int(r)) not in off]

    def fit_resolution(self, workflow_id, resolution, offered=(480, 720, 768, 1080)):
        """(the resolution a job is made at, a note saying why it is not the one asked for, or ""). A switched-off one
        steps down to the largest allowed below it, or else up to the smallest allowed above it. ValueError when the
        workflow has none left."""
        asked = _int(resolution)
        allowed = self.allowed_resolutions(workflow_id, offered)
        if asked is None or asked in allowed or RESOLUTION_TIER.get(asked) is None:
            return resolution, ""
        if not allowed:
            raise ValueError("Every resolution of this workflow is switched off for now. Try another workflow.")
        below = [r for r in allowed if r < asked]
        used = max(below) if below else min(allowed)
        return used, "{}p is switched off for this workflow, so it is made at {}p.".format(asked, used)

    @staticmethod
    def _json(text):
        try:
            found = json.loads(text)
        except (TypeError, ValueError):
            return {}
        return found if isinstance(found, dict) else {}

    @property
    def daily_cap(self):
        """The most credits one user may spend in 24 hours, unless an admin set their own. 0 means no limit."""
        return int(float(self.db.setting("daily_cap", 0)))

    def cap_for(self, user):
        own = user.get("daily_cap")
        return self.daily_cap if own is None else own

    def spent_today(self, user_id):
        """Credits spent in the last 24 hours: charges, less what was refunded."""
        row = self.db.one("SELECT SUM(amount) n FROM credit_events WHERE user_id = ? AND reason IN ('generation', 'refund', 'agent') "
                          "AND created > ?", (user_id, time.time() - 86400))
        return max(0, -(row["n"] or 0))

    def cap_problem(self, user_id, amount):
        """Why a charge of `amount` would go over the user's daily limit, or None. Admins have no limit. An early no,
        before the work starts: charge() checks it again, with the user's row locked, as it takes the credits."""
        return self._cap_problem(user_id, amount)

    def _cap_problem(self, user_id, amount, lock=False):
        """cap_problem; with `lock` (inside a transaction), the user's row stays locked until it ends, so a charge made
        at the same moment waits for this one and counts it in what was spent."""
        if PREPAID.get() is not None:   # a plan's step: its plan's whole price was checked at approval, and reserved
            from . import guardrails   # ...and it may not cost more than is left of what was approved
            return guardrails.plan_step_problem(self.db, PREPAID.get(), user_id, amount)
        user = self.db.one("SELECT role, daily_cap FROM users WHERE id = ?" + (" FOR UPDATE" if lock else ""), (user_id,))
        if not user or user["role"] == "admin" or amount <= 0:
            return None
        cap = self.cap_for(user)
        spent = self.spent_today(user_id)
        if cap and spent + amount > cap:
            return ("This needs {} credits. Your account can spend {} in 24 hours and has spent {} already. "
                    "Try again later, or ask an admin.".format(amount, cap, spent))
        return None

    def balance(self, user_id):
        row = self.db.one("SELECT credits FROM users WHERE id = ?", (user_id,))
        return row["credits"] if row else 0

    def charge(self, user_id, amount, reason, job_id=None, note="", project_id=None, cap=True):
        """Take credits if the user has enough. Returns False when they don't. `project_id`: the project it was spent in,
        when no job says so (a message to the agent). While a plan's step is queued (PREPAID), a generation's price is
        taken from what was reserved for the plan at its approval, and only what the reservation lacks from the balance.

        `cap` (the default): the user's daily limit holds. It is checked and the credits taken in one transaction with
        the user's row locked, so two charges at the same moment can't both pass a limit only one of them fits under
        (cap_problem(), asked first by the callers, is only an early no). Over it: OverCap (a 429 with cap_problem's
        words), and nothing is taken. cap=False for what was already used (charge_up_to) or what an admin decides."""
        if amount <= 0:
            return True
        plan = PREPAID.get()
        if plan is not None and reason == "generation":
            return self._charge_plan(user_id, plan, amount, reason, job_id, note, project_id)
        return self._charge(user_id, amount, reason, job_id, note, project_id, cap)

    def _charge_plan(self, user_id, plan, amount, reason, job_id, note, project_id):
        from . import guardrails   # a step never takes more than is left of its plan's approved reservation
        problem = guardrails.plan_step_problem(self.db, plan, user_id, amount)
        if problem:
            raise OverCap(problem)
        row = self.db.one("SELECT reserved_left FROM agent_plans WHERE id = ? AND user_id = ?", (plan, user_id))
        take = min(amount, row["reserved_left"]) if row else 0
        if take and not self.db.change("UPDATE agent_plans SET reserved_left = reserved_left - ? WHERE id = ? AND reserved_left >= ?",
                                       (take, plan, take)):
            take = 0
        rest = amount - take
        if rest and not self._charge(user_id, rest, reason, job_id, note, project_id):
            if take:   # the step is not queued: what it drew goes back to the reservation
                self.db.run("UPDATE agent_plans SET reserved_left = reserved_left + ? WHERE id = ?", (take, plan))
            return False
        return True

    def _charge(self, user_id, amount, reason, job_id=None, note="", project_id=None, cap=False):
        """The balance taken and its event logged in one transaction; with `cap`, the daily limit checked first under
        the user's row lock, which the UPDATE keeps until both are written."""
        with self.db.transaction():
            if cap:
                problem = self._cap_problem(user_id, amount, lock=True)
                if problem:
                    raise OverCap(problem)
            if not self.db.change("UPDATE users SET credits = credits - ? WHERE id = ? AND credits >= ?",
                                  (amount, user_id, amount)):
                return False
            self._log(user_id, -amount, reason, job_id, note, project_id)
        return True

    def charge_up_to(self, user_id, amount, reason, note="", project_id=None):
        """charge(), for what was already used (an answer's tokens): when the user has less, all they have is taken.
        Returns what was taken."""
        while amount > 0 and not self.charge(user_id, amount, reason, note=note, project_id=project_id, cap=False):
            amount = min(amount, self.balance(user_id))   # the balance changed between the two: try again with what is there
        return max(amount, 0)

    def add(self, user_id, amount, reason, job_id=None, note=""):
        """Give credits, or take them with a negative amount. A balance never goes below zero.
        Returns the change that was actually made. One statement, the user's row locked while it reads the balance: two
        changes at once (requests run side by side on the database's threads) can't both take what is only there once."""
        row = self.db.one("UPDATE users u SET credits = GREATEST(u.credits + ?, 0) FROM "
                          "(SELECT id, credits AS before FROM users WHERE id = ? FOR UPDATE) b WHERE u.id = b.id "
                          "RETURNING u.credits - b.before AS made", (amount, user_id))
        amount = row["made"] if row else 0
        if amount:
            self._log(user_id, amount, reason, job_id, note)
        return amount

    def _log(self, user_id, amount, reason, job_id, note="", project_id=None):
        self.db.run("INSERT INTO credit_events (user_id, amount, reason, job_id, note, created, project_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, amount, reason, job_id, note, time.time(), project_id))
