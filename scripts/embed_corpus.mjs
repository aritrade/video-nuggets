// Precompute MiniLM embeddings for the chat corpus, at build time.
//
// Runs the same model (Xenova/all-MiniLM-L6-v2) that the serverless function
// uses at query time, so the precomputed chunk vectors and the runtime query
// vector live in the same space. Also primes api/_models/ with the model files
// so they get bundled into the function (no cold-start network download).
//
// Usage: node scripts/embed_corpus.mjs
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const MODELS_DIR = join(ROOT, 'api', '_models');
const CORPUS = join(ROOT, 'api', '_data', 'corpus.json');
const OUT = join(ROOT, 'api', '_data', 'embeddings.json');
const MODEL_ID = 'Xenova/all-MiniLM-L6-v2';

const { pipeline, env } = await import('@xenova/transformers');
// Cache/download the model into the repo so it can be bundled with the function.
env.cacheDir = MODELS_DIR;
env.allowRemoteModels = true;

const corpus = JSON.parse(readFileSync(CORPUS, 'utf-8'));
const extractor = await pipeline('feature-extraction', MODEL_ID);

const vectors = [];
for (const chunk of corpus) {
  const out = await extractor(chunk.text, { pooling: 'mean', normalize: true });
  vectors.push(Array.from(out.data).map((x) => Math.round(x * 1e5) / 1e5));
}

const dims = vectors[0]?.length || 0;
writeFileSync(OUT, JSON.stringify({ model: MODEL_ID, dims, vectors }));
console.log(`[embed_corpus] embedded ${vectors.length} chunks (dims=${dims}) -> ${OUT}`);
console.log(`[embed_corpus] model cached under ${MODELS_DIR}`);
