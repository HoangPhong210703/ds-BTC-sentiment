import asyncio

from ner_model.gliner_model_service import GlinerModelService

SAMPLE = "Coinbase listed Solana after Ethereum's network upgrade."


async def main():
    svc = GlinerModelService()
    entities = await svc.predict_text(SAMPLE)
    print("Entities:", entities)

    found = {e["text"].lower() for e in entities}
    assert any("solana" in t for t in found), "Solana not detected"
    assert any("ethereum" in t for t in found), "Ethereum not detected"
    for e in entities:
        assert {"start", "end", "text", "label", "score"} <= set(e.keys()), e
    print("OK: GLiNER local inference satisfies the contract")


if __name__ == "__main__":
    asyncio.run(main())
