from dataclasses import dataclass


@dataclass
class Config:
    vocab_size: int = 256
    n_embd: int = 64
    n_head: int = 4
    n_layer: int = 4
    block_size: int = 128
    dropout: float = 0.1


# TODO: model goes here
