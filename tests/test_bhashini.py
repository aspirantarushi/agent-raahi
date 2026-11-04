"""bhashini.py, with a pretend Bhashini (no internet, no keys)."""

import base64
import json
import urllib.error

import pytest

import bhashini


class FakeBhashini:
    """Answers the config and compute calls the way the docs describe, and records what was sent."""

    def __init__(self, translated="The brother was arrested on 15 March 2024.", spoken="मेरा भाई जेल में है",
                 config_error=None):
        self.sent = []
        self.translated, self.spoken, self.config_error = translated, spoken, config_error

    def __call__(self, request, **k):
        body = json.loads(request.data)
        headers = {key.lower(): value for key, value in request.header_items()}
        self.sent.append({"url": request.full_url, "headers": headers, "body": body})
        if request.full_url == bhashini.CONFIG_URL:
            if self.config_error:
                raise urllib.error.HTTPError(request.full_url, self.config_error, "error", {}, None)
            task = body["pipelineTasks"][0]["taskType"]
            return Reply({"languages": [{"sourceLanguage": "hi", "targetLanguageList": ["en"]}],
                          "pipelineResponseConfig": [{"taskType": task, "config": [{"serviceId": f"service-{task}"}]}],
                          "pipelineInferenceAPIEndPoint": {"callbackUrl": "https://compute.example/inference",
                                                           "inferenceApiKey": {"name": "Authorization",
                                                                               "value": "session-key"}}})
        task = body["pipelineTasks"][0]["taskType"]
        if task == "translation":
            return Reply({"pipelineResponse": [{"taskType": "translation", "output": [
                {"source": body["inputData"]["input"][0]["source"], "target": self.translated}]}]})
        return Reply({"pipelineResponse": [{"taskType": "asr", "output": [{"source": self.spoken}]}]})


class Reply:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, *a):
        return json.dumps(self.data).encode()


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setattr(bhashini.llm, "_load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("BHASHINI_USER_ID", "test-user")
    monkeypatch.setenv("BHASHINI_API_KEY", "test-key")
    bhashini._config_cache.clear()


@pytest.fixture
def fake(monkeypatch, keys):
    f = FakeBhashini()
    monkeypatch.setattr(bhashini.urllib.request, "urlopen", f)
    return f


# ---------- the two calls, as in the docs ----------

def test_translation_uses_config_then_compute(fake):
    result = bhashini.translate("भाई को 15 मार्च 2024 को गिरफ़्तार किया गया।", "hi", "en")
    assert result.text == "The brother was arrested on 15 March 2024."
    config, compute = fake.sent
    assert config["url"] == bhashini.CONFIG_URL
    assert config["headers"]["userid"] == "test-user" and config["headers"]["ulcaapikey"] == "test-key"
    assert config["body"] == {"pipelineTasks": [{"taskType": "translation", "config": {"language": {
        "sourceLanguage": "hi", "targetLanguage": "en"}}}], "pipelineRequestConfig": {"pipelineId": bhashini.PIPELINE_ID}}
    assert compute["url"] == "https://compute.example/inference"
    assert compute["headers"]["authorization"] == "session-key"
    assert compute["body"]["pipelineTasks"][0]["config"]["serviceId"] == "service-translation"
    assert compute["body"]["inputData"] == {"input": [{"source": "भाई को 15 मार्च 2024 को गिरफ़्तार किया गया।"}]}


def test_config_is_reused(fake):
    bhashini.translate("एक", "hi", "en")
    bhashini.translate("दो", "hi", "en")
    assert [s["url"] for s in fake.sent].count(bhashini.CONFIG_URL) == 1


def test_older_response_shape_is_read(fake, monkeypatch):
    class Old(FakeBhashini):
        def __call__(self, request, **k):
            reply = super().__call__(request, **k)
            if request.full_url != bhashini.CONFIG_URL:
                return Reply({"taskType": "translation", "output": [{"source": "x", "target": "plain shape"}]})
            return reply
    monkeypatch.setattr(bhashini.urllib.request, "urlopen", Old())
    assert bhashini.translate("x", "hi", "en").text == "plain shape"


# ---------- privacy: filtered BEFORE sending ----------

@pytest.mark.parametrize("text", ["ফোন ৯৮৭৬৫৪৩২১০", "போன் ௯௮௭௬௫௪௩௨௧௦", "ਫ਼ੋਨ ੯੮੭੬੫ ੪੩੨੧੦", "ᱯᱷᱚᱱ ᱙᱘᱗᱖᱕᱔᱓᱒᱑᱐",
                                  "آدھار ۲۳۴۵ ۶۷۸۹ ۰۱۲۳", "email didi@example.com"])
def test_personal_numbers_never_reach_bhashini(fake, text):
    result = bhashini.translate(text, "bn", "en")
    sent = json.dumps([s["body"] for s in fake.sent], ensure_ascii=False)
    for digits in ("9876543210", "234567890123", "didi@example.com"):
        assert digits not in bhashini.privacy.normalise_digits(sent).replace(" ", "")
    assert result.removed


def test_translated_text_is_filtered_too(keys, monkeypatch):
    monkeypatch.setattr(bhashini.urllib.request, "urlopen", FakeBhashini(translated="call 9876543210"))
    assert "9876543210" not in bhashini.translate("x", "hi", "en").text


def test_same_language_is_not_sent(fake):
    assert bhashini.translate("Hello", "en", "en").text == "Hello" and fake.sent == []


# ---------- speech to text ----------

def test_speech_to_text(fake):
    result = bhashini.speech_to_text(b"RIFF fake", "hi")
    compute = fake.sent[1]["body"]
    assert compute["pipelineTasks"][0]["config"]["audioFormat"] == "wav"
    assert compute["pipelineTasks"][0]["config"]["samplingRate"] == 16000
    assert compute["inputData"] == {"audio": [{"audioContent": base64.b64encode(b"RIFF fake").decode()}]}
    assert result.text == "मेरा भाई जेल में है"


def test_spoken_numbers_are_filtered(keys, monkeypatch):
    monkeypatch.setattr(bhashini.urllib.request, "urlopen", FakeBhashini(spoken="मेरा नंबर ९८७६५४३२१० है"))
    result = bhashini.speech_to_text(b"RIFF", "hi")
    assert "[phone number removed]" in result.text and result.removed == {"a phone number": 1}


def test_empty_or_huge_recordings(fake):
    with pytest.raises(bhashini.BhashiniUnavailable, match="empty"):
        bhashini.speech_to_text(b"", "hi")
    with pytest.raises(bhashini.BhashiniUnavailable, match="too long"):
        bhashini.speech_to_text(b"0" * (bhashini.MAX_AUDIO_BYTES + 1), "hi")


# ---------- when Bhashini can't be used ----------

def test_not_set_up(monkeypatch):
    monkeypatch.setattr(bhashini.llm, "_load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("BHASHINI_USER_ID", raising=False)
    monkeypatch.delenv("BHASHINI_API_KEY", raising=False)
    assert not bhashini.configured()
    with pytest.raises(bhashini.BhashiniUnavailable, match="not set up"):
        bhashini.translate("नमस्ते", "hi", "en")


@pytest.mark.parametrize("code, words", [(401, "did not accept"), (403, "did not accept"), (500, "had a problem")])
def test_errors_become_friendly(keys, monkeypatch, code, words):
    monkeypatch.setattr(bhashini.urllib.request, "urlopen", FakeBhashini(config_error=code))
    with pytest.raises(bhashini.BhashiniUnavailable, match=words):
        bhashini.translate("नमस्ते", "hi", "en")
    assert not bhashini.supports("translation", "hi")


def test_no_internet(keys, monkeypatch):
    def fail(*a, **k):
        raise urllib.error.URLError("down")
    monkeypatch.setattr(bhashini.urllib.request, "urlopen", fail)
    with pytest.raises(bhashini.BhashiniUnavailable, match="internet"):
        bhashini.translate("नमस्ते", "hi", "en")


def test_keys_never_in_error_messages(keys, monkeypatch):
    monkeypatch.setattr(bhashini.urllib.request, "urlopen", FakeBhashini(config_error=401))
    with pytest.raises(bhashini.BhashiniUnavailable) as info:
        bhashini.translate("नमस्ते", "hi", "en")
    report = str(info.getrepr(showlocals=True, style="long"))
    assert "test-key" not in str(info.value)
    assert "test-key" not in report.split("def test_keys_never_in_error_messages")[-1].split("monkeypatch.setenv")[0]
    assert "'test-key'" not in report


def test_22_scheduled_languages_with_own_script_names():
    assert len(bhashini.LANGUAGES) == 22
    for code, (english, native) in bhashini.LANGUAGES.items():
        assert native and native != english, code


# ---------- the real Bhashini (only with keys) ----------

@pytest.mark.skipif(not bhashini.configured(), reason="No BHASHINI_USER_ID / BHASHINI_API_KEY: live test skipped")
def test_live_translation():
    result = bhashini.translate("मेरे भाई को 15 मार्च 2024 को गिरफ़्तार किया गया।", "hi", "en")
    assert "15" in result.text and "2024" in result.text
