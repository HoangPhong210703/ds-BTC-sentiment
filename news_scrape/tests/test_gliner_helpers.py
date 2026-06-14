# Run from the news_scrape/ directory so `ner_model` is importable.
from ner_model.gliner_model_service import update_entity_positions


def test_update_entity_positions_shifts_start_and_end():
    entities = [
        {"start": 0, "end": 3, "text": "BTC", "label": "Token Cryptocurrency", "score": 0.9},
        {"start": 5, "end": 8, "text": "ETH", "label": "Token Cryptocurrency", "score": 0.8},
    ]
    shifted = update_entity_positions(entities, 100)
    assert shifted[0]["start"] == 100 and shifted[0]["end"] == 103
    assert shifted[1]["start"] == 105 and shifted[1]["end"] == 108
    # Non-position fields are preserved
    assert shifted[0]["text"] == "BTC"
    assert shifted[1]["label"] == "Token Cryptocurrency"


def test_module_imports_without_torch_or_spacy():
    # Importing the module must not require heavy deps at import time.
    import ner_model.gliner_model_service as m
    assert hasattr(m, "GlinerModelService")
    # predict_text is an async method on the class, not a module-level function.
    assert hasattr(m.GlinerModelService, "predict_text")
