import os, time, math, json, threading, queue
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, ConcatDataset
import json
import sys, traceback

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

class CausalSelfAttention(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        assert cfg["embed_dim"] % cfg["n_heads"] == 0
        self.n_heads  = cfg["n_heads"]
        self.head_dim = cfg["embed_dim"] // cfg["n_heads"]
        self.qkv  = nn.Linear(cfg["embed_dim"], 3 * cfg["embed_dim"], bias=False)
        self.proj = nn.Linear(cfg["embed_dim"], cfg["embed_dim"], bias=False)
        self.drop = nn.Dropout(cfg["dropout"])
        self.register_buffer(
            "mask",
            torch.tril(torch.ones(cfg["block_size"], cfg["block_size"]))
                  .view(1, 1, cfg["block_size"], cfg["block_size"])
        )

    def forward(self, x):
        B, T, C = x.shape
        q, k, v = self.qkv(x).split(C, dim=2)
        q = q.view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        k = k.view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        v = v.view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        att = (q @ k.transpose(-2, -1)) / math.sqrt(self.head_dim)
        att = att.masked_fill(self.mask[:, :, :T, :T] == 0, float("-inf"))
        att = torch.softmax(att, dim=-1)
        att = self.drop(att)
        out = (att @ v).transpose(1, 2).contiguous().view(B, T, C)
        return self.proj(out)

class TransformerBlock(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.ln1  = nn.LayerNorm(cfg["embed_dim"])
        self.attn = CausalSelfAttention(cfg)
        self.ln2  = nn.LayerNorm(cfg["embed_dim"])
        self.ff   = nn.Sequential(
            nn.Linear(cfg["embed_dim"], 4 * cfg["embed_dim"]),
            nn.GELU(),
            nn.Linear(4 * cfg["embed_dim"], cfg["embed_dim"]),
            nn.Dropout(cfg["dropout"]),
        )

    def forward(self, x):
        x = x + self.attn(self.ln1(x))
        x = x + self.ff(self.ln2(x))
        return x

class TariqModel(nn.Module):
    def __init__(self, cfg, vocab_size: int):
        super().__init__()
        self.cfg        = cfg
        self.block_size = cfg["block_size"]
        self.tok_emb = nn.Embedding(vocab_size, cfg["embed_dim"])
        self.pos_emb = nn.Embedding(cfg["block_size"], cfg["embed_dim"])
        self.drop    = nn.Dropout(cfg["dropout"])
        self.blocks  = nn.Sequential(
            *[TransformerBlock(cfg) for _ in range(cfg["n_layers"])]
        )
        self.ln_f    = nn.LayerNorm(cfg["embed_dim"])
        self.head    = nn.Linear(cfg["embed_dim"], vocab_size, bias=False)
        self.tok_emb.weight = self.head.weight
        self.apply(self._init_weights)

    @staticmethod
    def _init_weights(m):
        if isinstance(m, (nn.Linear, nn.Embedding)):
            nn.init.normal_(m.weight, std=0.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.zeros_(m.bias)

    def expand_vocab(self, new_size: int):
        old = self.tok_emb.num_embeddings
        if new_size <= old:
            return
        dim     = self.cfg["embed_dim"]
        new_emb = nn.Embedding(new_size, dim)
        new_emb.weight.data[:old] = self.tok_emb.weight.data
        nn.init.normal_(new_emb.weight.data[old:], std=0.02)
        new_head        = nn.Linear(dim, new_size, bias=False)
        new_head.weight = new_emb.weight
        self.tok_emb    = new_emb.to(DEVICE)
        self.head       = new_head.to(DEVICE)

    def forward(self, idx, targets=None):
        B, T   = idx.shape
        pos    = torch.arange(T, device=idx.device)
        x      = self.drop(self.tok_emb(idx) + self.pos_emb(pos))
        x      = self.blocks(x)
        logits = self.head(self.ln_f(x))
        loss   = None
        if targets is not None:
            loss = nn.functional.cross_entropy(
                logits.view(-1, logits.size(-1)), targets.view(-1)
            )
        return logits, loss

    @torch.no_grad()
    def generate(self, idx, max_new_tokens=250, temperature=1.0, block_size=256):
        token_probs = [] # confidence
        for _ in range(max_new_tokens):
            idx_c     = idx[:, -block_size:]
            logits, _ = self(idx_c)
            logits    = logits[:, -1, :] / max(temperature, 1e-6)
            probs     = torch.softmax(logits, dim=-1)
            probs     = torch.clamp(probs, min=1e-8)
            probs     = probs / probs.sum(dim=-1, keepdim=True)
            nxt       = torch.multinomial(probs, num_samples=1)
            token_probs.append(probs[0, nxt[0, 0]].item())
            idx       = torch.cat([idx, nxt], dim=1)
        return idx, token_probs

def _safe_val(v): return 1e9 if v != v or v in [float("inf"), float("-inf")] else v

def save_progress(root, cfg, epoch, best_val, model, tok, opt, sched):
    d = os.path.join(root, "models", cfg["name"])
    os.makedirs(d, exist_ok=True)
    torch.save({
        "model_state":     model.state_dict(),
        "optimizer_state": opt.state_dict(),
        "scheduler_state": sched.state_dict(),
        "tokenizer_c2i":   tok.c2i,
        "vocab_size":      tok.vocab_size,
        "cfg":             cfg,
        "epoch":           epoch,
        "best_val":        best_val,
    }, os.path.join(d, "checkpoint.pt"))

def find_checkpoint(root, model_name=None):
    target = f"{model_name}.pt" if model_name else "Tariq0.5.5.pt"

    for dirpath, dirnames, filenames in os.walk(root):
        skip = {'__pycache__', '.git', 'node_modules', 'target', 'dist', '.venv'}
        dirnames[:] = [d for d in dirnames if d not in skip]
        for filename in filenames:
            if filename == target:
                full_path = os.path.join(dirpath, filename)
                name = os.path.splitext(filename)[0]
                return full_path, name

    return None, None

class CharTokenizer:
    def __init__(self, text=None, vocab=None):
        if vocab:
            self.c2i = vocab
        else:
            chars = sorted(set(text))
            self.c2i = {c:i for i,c in enumerate(chars)}
        self.i2c = {i:c for c,i in self.c2i.items()}
        self.vocab_size = len(self.c2i)

    def encode(self, text):
        return [self.c2i.get(c, 0) for c in text]

    def decode(self, ids):
        return "".join(self.i2c.get(i, "?") for i in ids)

    def extend(self, text):
        added = 0
        for c in text:
            if c not in self.c2i:
                self.c2i[c] = len(self.c2i)
                added += 1
        self.i2c = {i:c for c,i in self.c2i.items()}
        self.vocab_size = len(self.c2i)
        return added

class TextDataset(torch.utils.data.Dataset):
    def __init__(self, ids, block_size):
        self.ids = ids
        self.block_size = block_size

    def __len__(self):
        return max(0, len(self.ids) - self.block_size)

    def __getitem__(self, idx):
        x = self.ids[idx:idx+self.block_size]
        y = self.ids[idx+1:idx+self.block_size+1]
        return torch.tensor(x, dtype=torch.long), torch.tensor(y, dtype=torch.long)

CFG_KEYS   = ("cfg", "config", "model_config", "hparams")
STATE_KEYS = ("model_state", "model_state_dict", "state_dict", "model")
TOK_KEYS   = ("tokenizer_c2i", "vocab")

def _pick(d, *keys, default=None):
    for k in keys:
        if k in d: return d[k]
    return default

def load_checkpoint(ckpt_path):
    """
    Load a TariqGPT checkpoint robustly.
    Handles alternate key names for cfg, model state, and tokenizer.
    Returns (cfg, tok, model) or raises RuntimeError with a clear message.
    """
    data = torch.load(ckpt_path, map_location=DEVICE, weights_only=False)

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Expected a dict checkpoint, got {type(data).__name__}.\n"
            "Did you save just the state_dict instead of a full checkpoint?")

    print(f"[interpreter] Checkpoint keys: {list(data.keys())}", file=sys.stderr)

    cfg_key = next((k for k in CFG_KEYS if k in data), None)
    if cfg_key is not None:
        raw_cfg = data[cfg_key]
        cfg = {
            "name":       _pick(raw_cfg, "name",
                                default=os.path.splitext(
                                    os.path.basename(ckpt_path))[0]),
            "embed_dim":  _pick(raw_cfg, "embed_dim", "d_model", "hidden_size",
                                "n_embd", "hidden_dim"),
            "n_heads":    _pick(raw_cfg, "n_heads", "num_heads",
                                "num_attention_heads"),
            "n_layers":   _pick(raw_cfg, "n_layers", "num_layers", "n_layer",
                                "num_hidden_layers"),
            "block_size": _pick(raw_cfg, "block_size", "max_seq_len",
                                "context_length", "seq_len",
                                "max_position_embeddings", default=256),
            "dropout":    _pick(raw_cfg, "dropout", "dropout_prob",
                                "attention_dropout", default=0.0),
        }
        missing = [k for k in ("embed_dim", "n_heads", "n_layers") if cfg[k] is None]
        if missing:
            raise RuntimeError(
                f"Config found under '{cfg_key}' but missing critical fields: {missing}\n"
                f"Raw config keys: {list(raw_cfg.keys())}\n"
                f"Raw config values: {dict(list(raw_cfg.items())[:20])}")
        print(f"[interpreter] Config ('{cfg_key}'): {cfg}", file=sys.stderr)
    else:
        # infer from weight shapes
        state_key  = next((k for k in STATE_KEYS if k in data), None)
        raw_state  = data[state_key] if state_key else data
        if any(k.startswith("_orig_mod.") for k in raw_state):
            raw_state = {k.replace("_orig_mod.", "", 1): v for k, v in raw_state.items()}

        emb_w = raw_state.get("tok_emb.weight") or raw_state.get("embedding.weight")
        pos_w = raw_state.get("pos_emb.weight")
        n_lay = sum(1 for k in raw_state if k.endswith(".ln1.weight"))
        hd_w  = next((v for k, v in raw_state.items() if "ff.0.weight" in k), None)

        if emb_w is None:
            raise RuntimeError(
                f"'cfg'/'config' key missing and could not infer shape "
                f"(no tok_emb.weight found).\n"
                f"Checkpoint keys: {list(data.keys())}")

        embed_dim  = emb_w.shape[1]
        cfg = {
            "name":       os.path.splitext(os.path.basename(ckpt_path))[0],
            "embed_dim":  embed_dim,
            "n_heads":    max(1, embed_dim // 64),
            "n_layers":   n_lay or 4,
            "block_size": pos_w.shape[0] if pos_w is not None else 256,
            "dropout":    0.0,
        }
        print(f"[interpreter] WARNING: no config key — inferred: {cfg}", file=sys.stderr)

    tok_key = next((k for k in TOK_KEYS if k in data), None)
    if tok_key is None:
        raise RuntimeError(
            f"No tokenizer found.\n"
            f"Expected one of {TOK_KEYS}.\n"
            f"Keys present: {list(data.keys())}")
    tok = CharTokenizer(vocab=data[tok_key])
    vocab_size = max(data.get("vocab_size", tok.vocab_size), tok.vocab_size)

    state_key = next((k for k in STATE_KEYS if k in data), None)
    if state_key is None:
        if all(isinstance(v, torch.Tensor) for v in data.values()):
            state = data
            print("[interpreter] No state_dict key — treating whole file as state_dict.",
                  file=sys.stderr)
        else:
            raise RuntimeError(
                f"Cannot find model weights.\n"
                f"Expected one of {STATE_KEYS}.\n"
                f"Keys present: {list(data.keys())}")
    else:
        state = data[state_key]

    # strip torch.compile prefix
    if any(k.startswith("_orig_mod.") for k in state):
        state = {k.replace("_orig_mod.", "", 1): v for k, v in state.items()}

    model = TariqModel(cfg, vocab_size).to(DEVICE)

    ckpt_vocab = state.get("tok_emb.weight")
    if ckpt_vocab is not None and ckpt_vocab.shape[0] != vocab_size:
        print(f"[interpreter] Vocab mismatch ckpt={ckpt_vocab.shape[0]} "
              f"tok={vocab_size} — skipping embeddings.", file=sys.stderr)
        state = {k: v for k, v in state.items()
                 if k not in ("tok_emb.weight", "head.weight")}
        model.load_state_dict(state, strict=False)
    else:
        missing, unexpected = model.load_state_dict(state, strict=False)
        if missing:
            print(f"[interpreter] Missing keys ({len(missing)}): {missing[:10]}",
                  file=sys.stderr)
        if unexpected:
            print(f"[interpreter] Unexpected keys ({len(unexpected)}): {unexpected[:10]}",
                  file=sys.stderr)

    model.eval()

    # NaN guard
    nan_params = [n for n, p in model.named_parameters() if torch.isnan(p).any()]
    if nan_params:
        print(f"[interpreter] NaN in: {nan_params}", file=sys.stderr)
        raise RuntimeError(f"NaN weights detected in {len(nan_params)} parameter(s) — "
                           "model is corrupted.")

    n_params = sum(p.numel() for p in model.parameters())
    print(f"[interpreter] OK — {cfg.get('name','?')}  "
          f"params={n_params/1e6:.2f}M  vocab={tok.vocab_size}", file=sys.stderr)

    return cfg, tok, model



import re as _re

def extract_clean_response(text: str) -> str:
    # normalize weird spacing artifacts
    text = _re.sub(r"(a\s*s\s*s\s*i\s*s\s*t\s*a\s*n\s*t)", "assistant", text, flags=_re.I)
    text = _re.sub(r"(u\s*s\s*e\s*r)", "user", text, flags=_re.I)
    text = _re.sub(r"(t\s*a\s*r\s*i\s*q)", "tariq", text, flags=_re.I)

    # cut everything after user: or tariq: (they signal a new speaker turn)
    text = _re.split(r"(?i)user:", text)[0]
    text = _re.split(r"(?i)tariq:", text)[0]

    # keep last assistant section only
    parts = _re.split(r"(?i)assistant:", text)
    text = parts[-1] if len(parts) > 1 else text

    # cleanup spacing
    text = _re.sub(r"\s{2,}", " ", text)

    return text.strip()

def main():
    
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

    if getattr(sys, 'frozen', False):
        root = os.path.dirname(sys.executable)
    else:
        root = os.path.dirname(os.path.abspath(__file__))

    max_tokens  = int(sys.argv[1])   if len(sys.argv) > 1 else 250
    temperature = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    model_name  = sys.argv[3]        if len(sys.argv) > 3 else None

    ckpt_path, found_name = find_checkpoint(root, model_name)
    if ckpt_path is None:
        print(f"No checkpoint found! Tried to find: "
              f"{model_name if model_name else 'Tariq0.5'}", file=sys.stderr)
        sys.exit(1)

    print(f"Using model: {found_name} ({ckpt_path})", file=sys.stderr)
    print(f"Using device: {DEVICE}", file=sys.stderr)

    try:
        cfg, tok, model = load_checkpoint(ckpt_path)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    prompt = sys.stdin.read().strip()
    if not prompt:
        print("No prompt received.", file=sys.stderr)
        sys.exit(1)

    ids        = torch.tensor([tok.encode(prompt)], dtype=torch.long, device=DEVICE)
    input_len  = ids.shape[1]
    block_size = min(cfg["block_size"], 256)
    out_ids, token_probs = model.generate(
        ids, max_new_tokens=max_tokens,
        temperature=temperature, block_size=block_size)
    out_text = tok.decode(out_ids[0][input_len:].tolist())

    out_text = extract_clean_response(out_text)
    print(json.dumps({"response": out_text, "token_probs": token_probs}))

if __name__ == "__main__":
    main()