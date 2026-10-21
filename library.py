"""The founder's documents: files they upload and earlier reports from the app,
read by the team and questioned by the founder.

An upload is kept as its passages (extract.py), never as the file, in memory
or in PostgreSQL. A request names the uploads and earlier reports it brings,
by id; each agent then reads the passages that bear on its own work, chosen
by how well they match it (BM25) within a budget, fenced as the founder's
material and marked so it can cite them: [D1 · page 3] for an upload,
[R1 · Launch Strategy] for an earlier report. The founder can also ask a
question of any of them (answer); the Chief of Staff answers from the
passages alone, citing each.
"""

import math
import re
import threading
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from typing import NamedTuple, Protocol

from pydantic import BaseModel, Field

from extract import Extracted, Passage

# Uploads kept, the newest first; an older one must be uploaded again.
KEEP_UPLOADS = 500
# What one agent reads of the founder's documents, in characters.
BUDGET = 9_000
ANSWER_BUDGET = 14_000
UPLOAD_ID = r"^[0-9a-f]{32}$"


class Upload(BaseModel):
    id: str
    name: str
    size: int
    created_at: datetime
    document: Extracted


class UploadSummary(BaseModel):
    id: str
    name: str
    kind: str
    parts: str
    size: int
    characters: int
    warnings: list[str]
    preview: str = Field(description="The start of its text, to show it was read.")


def summary_of(upload: Upload) -> UploadSummary:
    text = " ".join(p.text for p in upload.document.passages[:2])
    return UploadSummary(
        id=upload.id, name=upload.name, kind=upload.document.kind, parts=upload.document.parts, size=upload.size,
        characters=upload.document.characters, warnings=upload.document.warnings,
        preview=" ".join(text.split())[:280],
    )


def file_name(name: str) -> str:
    """A file's name as the founder gave it, without a folder or characters
    that cannot be shown."""
    name = re.split(r"[/\\]", re.sub(r"[\x00-\x1f\x7f]", "", name))[-1].strip()
    return name[:200] or "Untitled"


class UploadBackend(Protocol):
    def add(self, upload: Upload) -> None: ...

    def get(self, upload_id: str) -> Upload | None: ...


class MemoryUploads:
    """Uploads in this process's memory: lost when the API restarts."""

    def __init__(self):
        self._lock = threading.Lock()
        self._uploads: dict[str, Upload] = {}

    def add(self, upload: Upload) -> None:
        with self._lock:
            self._uploads[upload.id] = upload
            while len(self._uploads) > KEEP_UPLOADS:
                self._uploads.pop(next(iter(self._uploads)))

    def get(self, upload_id: str) -> Upload | None:
        with self._lock:
            return self._uploads.get(upload_id)


class UploadStore:
    def __init__(self, backend: UploadBackend | None = None):
        self.backend: UploadBackend = backend or MemoryUploads()

    def use(self, backend: UploadBackend) -> None:
        self.backend = backend

    def add(self, name: str, size: int, document: Extracted) -> Upload:
        upload = Upload(id=uuid.uuid4().hex, name=file_name(name), size=size, created_at=datetime.now(timezone.utc),
                        document=document)
        self.backend.add(upload)
        return upload

    def get(self, upload_id: str) -> Upload:
        upload = self.backend.get(upload_id)
        if upload is None:
            raise UploadNotFound(upload_id)
        return upload


class UploadNotFound(KeyError):
    """No upload has this id, or it is no longer kept."""


uploads = UploadStore()


# ---- A request's sources ----

class Source(NamedTuple):
    ref: str
    name: str
    kind: str
    passages: list[Passage]


def sources(upload_ids: list[str], report_ids: list[str]) -> list[Source]:
    """The uploads (D1, D2...) and earlier reports (R1, R2...) a request
    brings, as passages. Raises UploadNotFound or ReportNotFound for one that
    is not there."""
    from document import texts
    from reports import store

    found = []
    for number, upload_id in enumerate(upload_ids, start=1):
        upload = uploads.get(upload_id)
        found.append(Source(f"D{number}", upload.name, f"{upload.document.kind}, {upload.document.parts}",
                            upload.document.passages))
    for number, session_id in enumerate(report_ids, start=1):
        report = store.get(session_id)
        passages = [Passage(where=where.removeprefix("Team report · "), text=text) for where, text in texts(report)]
        kind = "investment proposal" if report.proposal else "team report"
        found.append(Source(f"R{number}", report.title, f"an earlier {kind} from this app", passages))
    return found


def describe(found: list[Source]) -> list[str]:
    """Each source in a line, for the team's report: "D1: plan.pdf (PDF, 12 pages)"."""
    return [f"{source.ref}: {source.name} ({source.kind})" for source in found]


# ---- Choosing the passages that bear on the work ----

_STOP = set(
    "the and for with that this from are was were will would should could can have has had not but you your "
    "our their they them its into over under about what which who whom when where how all any each more most "
    "than then also just only very such per a an of to in on at by as is it be or if so no do".split()
)


def _words(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9][a-z0-9$€£%.-]*", text.lower())
            if word not in _STOP and (len(word) > 2 or word.isdigit())]


def _ranked(found: list[Source], focus: str) -> list[tuple[float, int, Source, Passage]]:
    """Every passage scored against `focus` by BM25, best first; in document
    order when there is no focus."""
    entries = [(source, passage) for source in found for passage in source.passages]
    if not entries:
        return []
    query = set(_words(focus))
    bags = [Counter(_words(passage.text)) for _, passage in entries]
    average = sum(sum(bag.values()) for bag in bags) / len(bags) or 1
    holding = Counter(word for bag in bags for word in bag if word in query)
    scored = []
    for order, ((source, passage), bag) in enumerate(zip(entries, bags)):
        size = sum(bag.values())
        score = 0.0
        for word in query & bag.keys():
            idf = math.log(1 + (len(bags) - holding[word] + 0.5) / (holding[word] + 0.5))
            frequency = bag[word]
            score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * size / average))
        scored.append((score, order, source, passage))
    return sorted(scored, key=lambda entry: (-entry[0], entry[1])) if query else sorted(scored, key=lambda e: e[1])


def mark(source: Source, passage: Passage) -> str:
    return f"[{source.ref} · {passage.where}]"


def marks_in(text: str) -> list[str]:
    """The marks cited in `text`, in order, each on its own: a model may put
    two in one pair of brackets ("[D1 · page 3; D3 · sheet Revenue]")."""
    found = []
    for inside in re.findall(r"\[([^\[\]\n]+)\]", text):
        found += [f"[{part.strip()}]" for part in re.split(r";\s*|,\s*(?=[DR]\d)", inside)
                  if re.match(r"\s*[DR]\d+ · ", part)]
    return found


def excerpts(found: list[Source], focus: str, budget: int = BUDGET) -> str:
    """The passages that bear most on `focus`, within `budget` characters, each
    under its mark, grouped by source in their own order. Each source first
    gets an equal share of the budget (and at least its best passage), so a
    long report cannot crowd out a short file, which is read whole if it fits;
    what is left goes to the best passages of any source."""
    ranked = _ranked(found, focus)
    chosen: set[int] = set()
    used = 0
    share = budget // max(len(found), 1)
    for source in found:
        taken = 0
        for _, order, _, passage in (entry for entry in ranked if entry[2] is source):
            if taken and taken + len(passage.text) > share:
                continue
            chosen.add(order)
            taken += len(passage.text)
        used += taken
    for _, order, _, passage in ranked:
        if order not in chosen and used + len(passage.text) <= budget:
            chosen.add(order)
            used += len(passage.text)
    lines = []
    for source in found:
        picked = [entry for entry in ranked if entry[2] is source and entry[1] in chosen]
        if not picked:
            continue
        lines.append(f"{source.ref}: {source.name} ({source.kind})")
        for _, _, _, passage in sorted(picked, key=lambda entry: entry[1]):
            lines.append(f"{mark(source, passage)} {passage.text}")
        lines.append("")
    return "\n".join(lines).strip()


def for_prompt(upload_ids: list[str], report_ids: list[str], focus: str, budget: int = BUDGET) -> str:
    """The founder's documents as an agent reads them: the passages for its
    work, fenced as the founder's, with how to cite them; empty without any.
    A document no longer kept is left out, not an error, mid-run."""
    from guardrails import fence

    if not upload_ids and not report_ids:
        return ""
    try:
        found = sources(upload_ids, report_ids)
    except KeyError:
        return ""
    text = excerpts(found, focus, budget)
    if not text:
        return ""
    return ("The founder's documents. Use what bears on your work, and cite each passage you use by its mark, "
            f"each in its own brackets, such as {mark(found[0], found[0].passages[0])}:\n"
            f"{fence(text, 'the founder’s documents')}")


# ---- Questions about the documents ----

class Answer(BaseModel):
    answer: str = Field(description="The answer, in markdown, citing each passage it uses by its mark.")
    cited: list[str] = Field(default_factory=list, description="The marks of the passages the answer cites.")


class Cited(BaseModel):
    mark: str
    name: str
    where: str
    text: str = Field(description="The passage, or its start.")


class Answered(BaseModel):
    answer: str
    sources: list[Cited]


ANSWERER = (
    "You are the Chief of Staff of a startup founding team. The founder asks a question about documents: "
    "their own files, or reports the team wrote earlier. Answer from the passages given and nothing else, "
    "plainly and briefly, in markdown. Cite every claim by the mark of the passage it comes from, such as "
    "[D1 · page 3], right after it, each mark in its own brackets. If the passages do not answer the "
    "question, say what they do say and what is missing; never fill the gap from elsewhere."
)


def answer(question: str, upload_ids: list[str], report_ids: list[str],
           ask: Callable[[str, str], Answer]) -> Answered:
    """The Chief of Staff's answer to `question` from the documents' passages
    that bear on it, with the passages it cites. `ask(system, human)` makes the
    model call, so the API chooses the model and its effort."""
    from guardrails import RULES, fence, unfenced

    found = sources(upload_ids, report_ids)
    text = excerpts(found, question, ANSWER_BUDGET)
    human = (f"The founder's question:\n{fence(question, 'founder')}\n\n"
             f"The passages:\n{fence(text, 'the founder’s documents')}")
    reply = ask(ANSWERER + RULES, human)
    by_mark = {mark(source, passage): (source, passage) for source in found for passage in source.passages}
    marks = list(dict.fromkeys(marks_in(" ".join(reply.cited) + " " + reply.answer)))
    cited = [
        Cited(mark=m, name=by_mark[m][0].name, where=by_mark[m][1].where, text=by_mark[m][1].text[:400])
        for m in marks if m in by_mark
    ]
    return Answered(answer=unfenced(reply.answer).strip(), sources=cited)
