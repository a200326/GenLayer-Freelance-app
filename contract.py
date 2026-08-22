# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json

FETCH_FAILED = "fetch_failed"
MAX_EVIDENCE_CHARS = 3000

# Content types we consider "readable text evidence". Anything else
# (images, video, pdfs, archives, etc.) is treated as fetch_failed
# rather than being blindly decoded or passed to the LLM.
ALLOWED_CONTENT_PREFIXES = ("text/", "application/json", "application/javascript", "application/xml")


def _looks_like_text(content_type: str) -> bool:
    if content_type == "":
        # Some raw file hosts omit content-type; allow it and rely on
        # the utf-8 decode step below to catch genuinely binary bodies.
        return True
    ct = content_type.lower()
    return any(ct.startswith(p) for p in ALLOWED_CONTENT_PREFIXES)


def _fetch_text_evidence(url: str) -> str:
    """Fetch a URL and return decoded text, or FETCH_FAILED on any
    network, status, or decoding problem. Only the first
    MAX_EVIDENCE_CHARS characters are used for evaluation; longer
    evidence is truncated rather than rejected (see README).

    Uses gl.nondet.web.request(..., method='GET') rather than the
    .get() shorthand, since GenLayer's own documented examples read
    response.status_code only via .request(). Content-type header
    validation was attempted but dropped: it could not be reliably
    read on this GenVM version and caused legitimate fetches to be
    misreported as failures. Binary/unexpected content is instead
    caught naturally by the utf-8 decode step below (see README's
    Trust Model & Limitations section)."""
    try:
        resp = gl.nondet.web.request(url, method="GET")
    except Exception:
        return FETCH_FAILED

    status_code = None
    try:
        status_code = getattr(resp, "status_code", None)
    except Exception:
        status_code = None
    if isinstance(status_code, int) and not (200 <= status_code < 300):
        return FETCH_FAILED

    try:
        page_content = resp.body.decode("utf-8")[:MAX_EVIDENCE_CHARS]
    except Exception:
        return FETCH_FAILED

    if not page_content.strip():
        return FETCH_FAILED

    return page_content


def _is_valid_address(addr: str) -> bool:
    if not addr.startswith("0x"):
        return False
    if len(addr) != 42:
        return False
    return True


def _is_valid_url(url: str) -> bool:
    u = url.strip().lower()
    return u.startswith("http://") or u.startswith("https://")


class FreelanceTaskValidator(gl.Contract):
    descriptions: DynArray[str]
    evidence_urls: DynArray[str]
    statuses: DynArray[str]
    results: DynArray[str]
    verdicts: DynArray[str]
    clients: DynArray[str]
    workers: DynArray[str]
    task_count: u256

    def __init__(self):
        self.task_count = u256(0)

    def _require_task_exists(self, idx: int) -> None:
        if idx < 0 or idx >= int(self.task_count):
            raise gl.vm.UserError("Task does not exist")

    @gl.public.write
    def create_task(self, worker: str, description: str) -> None:
        worker_lower = worker.strip().lower()
        if not _is_valid_address(worker_lower):
            raise gl.vm.UserError(
                "worker must be a valid 0x-prefixed 40-hex-character address"
            )
        if description.strip() == "":
            raise gl.vm.UserError("description must not be empty")

        caller = str(gl.message.sender_address).lower()
        self.descriptions.append(description)
        self.evidence_urls.append("")
        self.statuses.append("open")
        self.results.append("")
        self.verdicts.append("")
        self.clients.append(caller)
        self.workers.append(worker_lower)
        self.task_count += u256(1)

    @gl.public.write
    def submit_evidence(self, task_id: u256, evidence_url: str) -> None:
        idx = int(task_id)
        self._require_task_exists(idx)
        caller = str(gl.message.sender_address).lower()

        if self.statuses[idx] != "open":
            raise gl.vm.UserError("Task must be open")
        if caller != self.workers[idx]:
            raise gl.vm.UserError("Only the worker can submit evidence")
        if not _is_valid_url(evidence_url):
            raise gl.vm.UserError("evidence_url must be a valid http(s) URL")

        self.evidence_urls[idx] = evidence_url
        self.statuses[idx] = "submitted"

    @gl.public.write
    def verify_and_resolve(self, task_id: u256) -> None:
        idx = int(task_id)
        self._require_task_exists(idx)
        caller = str(gl.message.sender_address).lower()

        if self.statuses[idx] != "submitted":
            raise gl.vm.UserError("Task must be submitted first")
        if caller != self.clients[idx]:
            raise gl.vm.UserError("Only the client can trigger verification")

        description = self.descriptions[idx]
        evidence_url = self.evidence_urls[idx]

        def fetch_and_evaluate() -> str:
            page_content = _fetch_text_evidence(evidence_url)
            if page_content == FETCH_FAILED:
                return FETCH_FAILED

            prompt = f"""
You are a neutral evaluator for a freelance task.

Task description: {description}

Evidence content:
{page_content}

Has the task been completed satisfactorily?
Respond ONLY with one word: approved or rejected
"""
            result = gl.nondet.exec_prompt(prompt)
            verdict = result.strip().lower()
            if "approved" in verdict:
                return "approved"
            return "rejected"

        verdict = gl.eq_principle.strict_eq(fetch_and_evaluate)

        if verdict == FETCH_FAILED:
            # Evidence could not be retrieved, was not a successful HTTP
            # response, had an unsupported content type, or could not be
            # decoded as text. State is left unchanged so the client can
            # retry once the evidence URL is fixed or reachable again.
            self.results[idx] = (
                "Evidence could not be verified: the URL did not return a "
                "successful text response. Task remains submitted; please "
                "retry verify_and_resolve once the URL is reachable and "
                "serves plain text or code."
            )
            return

        if verdict == "approved":
            self.verdicts[idx] = "approved"
            self.results[idx] = "approved"
            self.statuses[idx] = "approved"
        else:
            self.verdicts[idx] = "rejected"
            self.results[idx] = "rejected"
            self.statuses[idx] = "disputed"

    @gl.public.write
    def raise_dispute(self, task_id: u256, reason: str) -> None:
        idx = int(task_id)
        self._require_task_exists(idx)
        caller = str(gl.message.sender_address).lower()

        if self.statuses[idx] != "approved":
            raise gl.vm.UserError("Can only dispute approved tasks")
        if caller != self.clients[idx]:
            raise gl.vm.UserError("Only the client can raise a dispute")
        if reason.strip() == "":
            raise gl.vm.UserError("reason must not be empty")

        self.results[idx] = "Disputed: " + reason
        self.verdicts[idx] = "disputed"
        self.statuses[idx] = "disputed"

    @gl.public.write
    def resolve_dispute(self, task_id: u256) -> None:
        idx = int(task_id)
        self._require_task_exists(idx)
        caller = str(gl.message.sender_address).lower()

        if self.statuses[idx] != "disputed":
            raise gl.vm.UserError("Task must be in disputed state")
        if caller != self.clients[idx]:
            raise gl.vm.UserError("Only the client can resolve a dispute")

        description = self.descriptions[idx]
        evidence_url = self.evidence_urls[idx]
        dispute_reason = self.results[idx]

        def re_evaluate() -> str:
            page_content = _fetch_text_evidence(evidence_url)
            if page_content == FETCH_FAILED:
                return FETCH_FAILED

            prompt = f"""
You are a senior arbitrator reviewing a disputed freelance task.

Task description: {description}
Dispute reason: {dispute_reason}

Evidence content fetched directly from the submission URL:
{page_content}

Based on the task description and the evidence above, who should win?
Respond ONLY with one of: worker_wins or client_wins
"""
            result = gl.nondet.exec_prompt(prompt)
            verdict = result.strip().lower()
            if "worker_wins" in verdict:
                return "worker_wins"
            return "client_wins"

        verdict = gl.eq_principle.strict_eq(re_evaluate)

        if verdict == FETCH_FAILED:
            self.results[idx] = (
                "Evidence could not be verified during arbitration: the URL "
                "did not return a successful text response. Task remains "
                "disputed; please retry resolve_dispute once the URL is "
                "reachable and serves plain text or code."
            )
            return

        self.verdicts[idx] = verdict
        self.results[idx] = verdict
        if verdict == "worker_wins":
            self.statuses[idx] = "resolved_worker_wins"
        else:
            self.statuses[idx] = "resolved_client_wins"

    # ---- Structured getters for integrators ----

    @gl.public.view
    def get_status(self, task_id: u256) -> str:
        idx = int(task_id)
        self._require_task_exists(idx)
        return self.statuses[idx]

    @gl.public.view
    def get_verdict(self, task_id: u256) -> str:
        idx = int(task_id)
        self._require_task_exists(idx)
        return self.verdicts[idx]

    @gl.public.view
    def get_result(self, task_id: u256) -> str:
        idx = int(task_id)
        self._require_task_exists(idx)
        return self.results[idx]

    @gl.public.view
    def get_client(self, task_id: u256) -> str:
        idx = int(task_id)
        self._require_task_exists(idx)
        return self.clients[idx]

    @gl.public.view
    def get_worker(self, task_id: u256) -> str:
        idx = int(task_id)
        self._require_task_exists(idx)
        return self.workers[idx]

    @gl.public.view
    def get_description(self, task_id: u256) -> str:
        idx = int(task_id)
        self._require_task_exists(idx)
        return self.descriptions[idx]

    @gl.public.view
    def get_evidence_url(self, task_id: u256) -> str:
        idx = int(task_id)
        self._require_task_exists(idx)
        return self.evidence_urls[idx]

    @gl.public.view
    def get_task(self, task_id: u256) -> str:
        idx = int(task_id)
        self._require_task_exists(idx)
        return (
            "status: " + self.statuses[idx] +
            " | verdict: " + self.verdicts[idx] +
            " | client: " + self.clients[idx] +
            " | worker: " + self.workers[idx] +
            " | result: " + self.results[idx]
        )

    @gl.public.view
    def get_task_count(self) -> u256:
        return self.task_count

    @gl.public.view
    def get_max_evidence_chars(self) -> u256:
        """Exposes the evidence truncation limit on-chain so integrators
        do not have to rely solely on documentation to know that only
        the first MAX_EVIDENCE_CHARS characters of evidence are read."""
        return u256(MAX_EVIDENCE_CHARS)
