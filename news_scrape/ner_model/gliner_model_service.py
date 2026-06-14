import asyncio
import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

GLINER_MODEL_NAME = os.getenv("GLINER_MODEL_NAME", "urchade/gliner_small-v2.1")
GLINER_THRESHOLD = float(os.getenv("GLINER_THRESHOLD", "0.5"))
GLINER_USE_ONNX = os.getenv("GLINER_USE_ONNX", "false").lower() in ("1", "true", "yes")
GLINER_SUPPORTED_LABELS: list[str] = [
    "Token Cryptocurrency",
    "Partially Algorithmic Stablecoin",
    "Lending",
    "Uncollateralized Lending",
    "Lending Pool",
    "NFT Lending",
    "RWA Lending",
    "Collateralized debt position CDP",
    "CDP Manager",
    "Liquidity Automation",
    "Liquidity manager",
    "Staking",
    "Staking Pool",
    "Restaking",
    "Liquid Staking",
    "Liquid Restaking",
    "Yield",
    "Yield Aggregator",
    "RWA",
    "Launchpad",
    "Leveraged Farming",
    "Farm",
    "Reserve Currency",
    "Indexes",
    "Synthetics",
    "Derivatives",
    "Liquidations",
    "Basis Trading",
    "Exchange",
    "Cexes",
    "Dexes",
    "Prediction Market",
    "Trading App",
    "NFT Marketplace",
    "DEX Aggregator",
    "Chain",
    "Bridge",
    "Cross Chain",
    "Wallet Address",
    "Contract Address",
    "DeFi Project",
    "NftFi",
    "Algo-Stables",
    "Governance Incentives",
    "Telegram Bot",
    "Normal Entity",
    "Business",
    "People",
    "Technology",
    "Concept",
]
NER_THRESHOLD: float = 0.5


labels = [
    "Token Cryptocurrency",
    "Lending",
    "Chain",
    "Exchange",
    "Bridge",
    "Staking",
    "Yield Aggregator",
    "Launchpad",
    "Normal Entity",
    "Business",
    "Wallet Address",
    "DeFi Project",
    "Concept",
    "NftFi",
    "Prediction Market",
    "Leveraged Farming",
    "Staking Pool",
    "Restaking",
    "NFT Marketplace",
    "Dexes",
    "Farm",
    "DEX Aggregator",
    "Cross Chain",
    "Uncollateralized Lending",
    "Partially Algorithmic Stablecoin",
    "Synthetics",
    "Derivatives",
    "Liquidations",
    "Basis Trading",
    "NFT Lending",
    "Cexes",
    "Gaming",
    "Trading App",
    "Liquidity manager",
    "Liquid Staking",
    "Yield",
    "Liquid Restaking",
    "RWA",
    "RWA Lending",
    "People",
    "Contract Address",
    "NFT Collection",
    "Decentralized Exchange",
]


@lru_cache(maxsize=1)
def _get_nlp():
    import spacy

    return spacy.load("en_core_web_sm")


def split_text_into_chunks(text, max_tokens=100):
    """
    Chia văn bản thành các chunk sao cho mỗi chunk không vượt quá max_tokens token.
    Văn bản được tách thành từng câu bằng spaCy, sau đó cộng dồn các câu cho đến khi đạt giới hạn token.

    Args:
        text (str): Văn bản đầu vào.
        max_tokens (int): Số token tối đa trong mỗi chunk.

    Returns:
        List[str]: Danh sách các chunk đã chia.
    """

    nlp = _get_nlp()
    doc = nlp(text)

    # Tách câu giữ nguyên khoảng trắng cuối câu
    sentences = [sent.text_with_ws for sent in doc.sents]

    chunks = []
    current_chunk = ""
    current_token_count = 0
    current_offset = 0
    for sentence in sentences:
        num_tokens = len(nlp(sentence))  # Đếm số token trong câu

        # Nếu thêm câu này vào mà vượt quá max_tokens, lưu chunk hiện tại và tạo chunk mới
        if current_token_count + num_tokens > max_tokens and current_chunk:
            chunks.append((current_chunk, current_offset))
            current_offset += len(current_chunk)
            current_chunk = ""
            current_token_count = 0

        # Thêm câu vào chunk hiện tại
        current_chunk += sentence
        current_token_count += num_tokens

    # Thêm chunk cuối nếu còn dữ liệu
    if current_chunk:
        chunks.append((current_chunk, current_offset))

    return chunks


def update_entity_positions(entities, chunk_offset):
    """
    Cập nhật vị trí thực thể từ chunk về vị trí trong văn bản gốc.

    Args:
        entities (List[Dict]): Danh sách thực thể từ mô hình.
        chunk_offset (int): Offset của chunk trong văn bản gốc.

    Returns:
        List[Dict]: Danh sách thực thể với vị trí chính xác trong văn bản gốc.
    """
    updated_entities = []
    for entity in entities:
        entity["start"] += chunk_offset
        entity["end"] += chunk_offset
        updated_entities.append(entity)
    return updated_entities


@lru_cache(maxsize=1)
def _get_model():
    from gliner import GLiNER

    logger.info("Loading GLiNER model %s (onnx=%s)", GLINER_MODEL_NAME, GLINER_USE_ONNX)
    if GLINER_USE_ONNX:
        model = GLiNER.from_pretrained(
            GLINER_MODEL_NAME, load_onnx_model=True, load_tokenizer=True
        )
    else:
        model = GLiNER.from_pretrained(GLINER_MODEL_NAME)
    logger.info("GLiNER model loaded.")
    return model


class GlinerModelService:
    def __init__(self, url: str | None = None):
        # `url` kept for backward compatibility; inference now runs locally.
        self.model = _get_model()

    async def predict_text(self, text: str) -> list[dict[str, Any]]:
        chunks = split_text_into_chunks(text)
        if not chunks:
            return []

        texts = [chunk for chunk, _offset in chunks]
        offsets = [offset for _chunk, offset in chunks]

        try:
            batched = await asyncio.to_thread(
                self.model.batch_predict_entities,
                texts,
                labels,
                threshold=GLINER_THRESHOLD,
            )
        except Exception as e:  # inference must never crash the scrape
            logger.error("GLiNER inference failed: %s", e, exc_info=True)
            return []

        if len(batched) != len(offsets):
            logger.warning(
                "GLiNER returned %d results for %d chunks; entities may be lost",
                len(batched),
                len(offsets),
            )

        sum_entity: list[dict[str, Any]] = []
        for entities, offset in zip(batched, offsets):
            sum_entity.extend(update_entity_positions(entities, offset))
        return sum_entity


if __name__ == "__main__":
    gliner_service = GlinerModelService()
    text = "Coinbase listed Solana after Ethereum's network upgrade."

    async def main():
        ner_results = await gliner_service.predict_text(text)
        print(ner_results)

    asyncio.run(main())
