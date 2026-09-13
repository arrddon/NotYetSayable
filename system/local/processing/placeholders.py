"""Pipeline contracts only. No AI prompts or production model calls yet."""


class PipelineNotConfigured(RuntimeError):
    pass


def ocr(image_path: str) -> str:
    raise PipelineNotConfigured("OCR engine has not been configured")


def ocr_postprocess(raw_text: str) -> dict:
    raise PipelineNotConfigured("OCR post-processing prompt is pending")


def analyze_q1(response: dict) -> dict:
    raise PipelineNotConfigured("Q1 prompt is pending")


def analyze_q2(response: dict) -> dict:
    raise PipelineNotConfigured("Q2 prompt is pending")


def analyze_q3(response: dict) -> dict:
    raise PipelineNotConfigured("Q3 prompt is pending")


def analyze_q4(response: dict) -> dict:
    raise PipelineNotConfigured("Q4 prompt is pending")


def interpret(responses: list[dict]) -> dict:
    raise PipelineNotConfigured("Priority / interpretation logic is pending")
