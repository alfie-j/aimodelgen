"""Builds a tiny random Qwen2-architecture model + tokenizer with the Qwen chat
template, so the training script can be smoke-tested on a CPU with no download."""
from pathlib import Path

QWEN_TEMPLATE = (
    "{% for message in messages %}"
    "{{'<|im_start|>' + message['role'] + '\n' + message['content'] + '<|im_end|>' + '\n'}}"
    "{% endfor %}"
    "{% if add_generation_prompt %}{{ '<|im_start|>assistant\n' }}{% endif %}"
)


def build(out: Path, corpus: list[str]) -> Path:
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers, decoders
    from transformers import PreTrainedTokenizerFast, Qwen2Config, Qwen2ForCausalLM

    out.mkdir(parents=True, exist_ok=True)
    tk = Tokenizer(models.BPE(unk_token=None))
    tk.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tk.decoder = decoders.ByteLevel()
    tk.train_from_iterator(corpus, trainers.BpeTrainer(vocab_size=600, special_tokens=["<|endoftext|>", "<|im_start|>", "<|im_end|>"],
                                                       initial_alphabet=pre_tokenizers.ByteLevel.alphabet()))
    tok = PreTrainedTokenizerFast(tokenizer_object=tk, eos_token="<|im_end|>", pad_token="<|endoftext|>",
                                  additional_special_tokens=["<|im_start|>", "<|im_end|>"])
    tok.chat_template = QWEN_TEMPLATE
    tok.save_pretrained(out)
    cfg = Qwen2Config(vocab_size=len(tok), hidden_size=64, intermediate_size=128, num_hidden_layers=2,
                      num_attention_heads=4, num_key_value_heads=2, max_position_embeddings=2048)
    Qwen2ForCausalLM(cfg).save_pretrained(out)
    return out
