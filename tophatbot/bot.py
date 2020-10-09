import json
import random
import warnings

from requests import Session

ENDPOINTS = {
    "home": "https://app.tophat.com",
    "csrf": "https://app.tophat.com/index_metadata/loginv2/",
    "login": "https://app.tophat.com/api/v3/authenticate/",
    "login_referer": "https://app.tophat.com/login",
    "file_tree": "https://app.tophat.com/api/v1/tree_data/",
    "question_data": "https://app.tophat.com/api/v3/page/{chapter_id}/question/",
    "answer": "https://app.tophat.com/api/v3/question/{question_id}/answer/",
}


class TopHatBot:
    COURSE_ID = None

    def __init__(self, username, password, course_id=None):
        self.username = username
        self.password = password
        self.course_id = course_id or self.COURSE_ID
        assert self.course_id is not None

        self.session = Session()
        # Doesn't seem necessary atm but just in case?
        self.session.headers["user-agent"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/86.0.4240.75 Safari/537.36"
        )
        # Requests to TopHat endpoints require a CSRF token
        self.session.headers["x-csrftoken"] = self._csrf_token

        self._jwt = self._login()

        # Requests to TopHat's authenticated endpoints
        # require the following auth header
        self.session.headers["authorization"] = f"Bearer {self._jwt}"

        self._chapters = self._get_chapters()
        self._questions = {}

    def _load_csrf_cookie(self):
        # sets a cookie called 'csrftoken'
        self.session.get(ENDPOINTS["csrf"])
        assert "csrftoken" in self.session.cookies

    @property
    def _csrf_token(self):
        if "csrftoken" not in self.session.cookies:
            self._load_csrf_cookie()
        return self.session.cookies["csrftoken"]

    @property
    def chapters(self):
        return self._chapters

    @property
    def questions(self):
        return self._questions

    def _login(self):
        r = self.session.post(
            ENDPOINTS["login"],
            headers={"referer": ENDPOINTS["login_referer"]},
            data={
                "username": self.username,
                "password": self.password,
            },
        )
        jwt = r.headers["TH_JWT"]
        return jwt

    def _get_chapters(self):
        r = self.session.get(
            ENDPOINTS["file_tree"],
            params={
                "module_id": "unitree",
                "course_id": self.course_id,
                "limit": 0,
            },
        )
        data = r.json()["objects"][0]["data"]
        tree_root = json.loads(data)
        chapters = tree_root["children"][0]["children"]

        return {
            chapter["display_name"]: chapter["id"]
            for chapter in chapters
        }

    def load_question_data(self, chapter_id):
        url = ENDPOINTS["question_data"].format(chapter_id=chapter_id)
        r = self.session.get(url)

        data = {}
        for question in r.json():
            # Skip questions we've already loaded
            if question["id"] in self._questions:
                continue

            question_id = question["id"]
            question_text = question["question"]

            if question["has_correct_answer"] is False:
                # If no correct answer is specified, pick a random one
                answer = [random.choice(question["choices"])]
            elif question["type"] == "match":
                # Matching questions delimit answers with '|,,| '.
                # Submit the correct matches in order
                answer = [
                    part
                    for s in question["correct_answers"]
                    for part in s.split("|,,| ")
                ]
            elif question["type"] == "sort":
                # Sorting questions delimit answers with commas (', ').
                # Submit the correct answers in order
                answer = [
                    part
                    for s in question["correct_answers"]
                    for part in s.split(", ")
                ]
            elif question["type"] in ("wa", "na"):
                # Written answer. Submit any of the correct answers
                answer = [random.choice(question["correct_answers"])]
            elif question["type"] == "fitbq":
                # Fill in the blank question.
                # TODO: Test case with multiple blanks.
                answer = [
                    v
                    for k, v in sorted(
                        question["correct_answers"].items()
                    )
                ]
            elif question["type"] == "mc":
                # Multiple choice. Submit the correct answer
                answer = question["correct_answers"]
            else:
                warnings.warn(
                    f'Unrecognized question type: {question["type"]}.'
                )
                answer = question["correct_answers"]

            data[question_id] = {
                "question": question_text,
                "answer": answer,
                "type": question["type"],
                "has_correct_answer": question["has_correct_answer"],
            }
        self._questions.update(data)

    def answer_question(self, question_id):
        try:
            answer = self._questions[question_id]["answer"]
        except KeyError:
            print(f"Question ID has not been loaded: {question_id}")
            return None

        url = ENDPOINTS["answer"].format(question_id=question_id)
        r = self.session.post(url, data={"answer": answer})
        return r.text


class Psych210Bot(TopHatBot):
    COURSE_ID = 250265

    @property
    def required_chapters(self):
        return {
            chapter: chapter_id
            for chapter, chapter_id in self.chapters.items()
            if chapter.startswith("Chapter")
            and "OPTIONAL" not in chapter
        }

    def _load_chapters(self, chapters=None):
        if chapters is None:
            chapters = []
        valid_prefixes = tuple(f"Chapter {i}" for i in chapters) or ""
        for chapter, chapter_id in self.required_chapters.items():
            if chapter.startswith(valid_prefixes):
                wrap_print(f"Loading chapter", chapter)
                self.load_question_data(chapter_id)

    def list_questions(self, chapters=None):
        self._load_chapters(chapters)
        for question_id, question in self.questions.items():
            wrap_print("Question", question["question"])
            if question["has_correct_answer"]:
                wrap_print("Correct answer", question["answer"])
            else:
                print(
                    "No correct answer specified. Selecting random response."
                )

    def run(self, chapters=None, delay: float = 0.3):
        from time import sleep

        self._load_chapters(chapters)

        for question_id, question in self.questions.items():
            wrap_print("Question", question["question"])
            if question["has_correct_answer"]:
                wrap_print("Correct answer", question["answer"])
            else:
                print(
                    "No correct answer specified. Selecting random response."
                )
            wrap_print("Submitting answer", question["answer"])

            resp = self.answer_question(question_id)
            wrap_print("Received response from server", resp)
            print()

            sleep(delay)


def _format_message(user, message):
    from textwrap import fill

    user, message = str(user), str(message)
    # Wrap lines, dropping all whitespace except newlines
    indent = " " * (len(user) + 2)
    lines = []
    for i, line in enumerate(message.split("\n")):
        if i == 0:
            filled = fill(line, subsequent_indent=indent)
        else:
            filled = fill(
                line, initial_indent=indent, subsequent_indent=indent
            )
        lines.append(filled)

    formatted = "\n".join(lines)
    return f"{user}: {formatted}"


def wrap_print(s1, s2, *args, **kwargs):
    print(_format_message(s1, s2), *args, **kwargs)
