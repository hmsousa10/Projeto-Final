import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import secrets

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import numpy as np
import onnxruntime as ort
ort.disable_telemetry_events()
from pydantic import BaseModel, Field
from tokenizers import Tokenizer

from request_limits import BodyLimitMiddleware

manifest=json.loads(Path('model.json').read_text())
MODEL_KEY=manifest['repository']+'@'+manifest['revision']+':quint8-avx2:mean128:v1'
gate=asyncio.Semaphore(1)


@asynccontextmanager
async def lifespan(app):
    token=Path(os.environ['SEMANTIC_TOKEN_FILE']).read_text().strip()
    if len(token)<32:
        raise RuntimeError('Semantic service requires a deployment secret')
    app.state.token=token
    tokenizer=Tokenizer.from_file('model/tokenizer.json')
    tokenizer.enable_truncation(max_length=manifest['max_tokens'])
    tokenizer.enable_padding()
    options=ort.SessionOptions()
    options.intra_op_num_threads=2
    options.inter_op_num_threads=1
    app.state.session=ort.InferenceSession('model/model_quint8_avx2.onnx',sess_options=options,providers=['CPUExecutionProvider'])
    app.state.tokenizer=tokenizer
    yield


app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
app.add_middleware(BodyLimitMiddleware,max_bytes=65536)


class Batch(BaseModel):
    model_config={'extra':'forbid'}
    texts: list[str]=Field(min_length=1,max_length=16)


@app.exception_handler(RequestValidationError)
async def invalid(request,error):
    return JSONResponse({'detail':'Invalid embedding batch'},status_code=422)


@app.get('/health')
def health():
    return {'status':'ready','model':MODEL_KEY,'dimensions':manifest['dimensions']}


def encode(texts):
    encoded=app.state.tokenizer.encode_batch(texts)
    arrays={'input_ids':np.array([e.ids for e in encoded],dtype=np.int64),
            'attention_mask':np.array([e.attention_mask for e in encoded],dtype=np.int64),
            'token_type_ids':np.array([e.type_ids for e in encoded],dtype=np.int64)}
    inputs={item.name:arrays[item.name] for item in app.state.session.get_inputs()}
    tokens=app.state.session.run(None,inputs)[0]
    mask=arrays['attention_mask'][...,None].astype(np.float32)
    vectors=(tokens*mask).sum(axis=1)/np.maximum(mask.sum(axis=1),1e-9)
    vectors=vectors/np.maximum(np.linalg.norm(vectors,axis=1,keepdims=True),1e-9)
    return vectors.tolist()


@app.post('/embed')
async def embed(data:Batch,request:Request):
    if not secrets.compare_digest(request.headers.get('authorization','').encode(),('Bearer '+app.state.token).encode()):
        raise HTTPException(401,'Embedding request not authorized')
    if any(not text.strip() or len(text)>2000 for text in data.texts):
        raise HTTPException(422,'Embedding texts must contain 1 to 2000 characters')
    try:
        await asyncio.wait_for(gate.acquire(),timeout=.1)
    except TimeoutError:
        raise HTTPException(429,'Embedding service busy')
    try:
        vectors=await asyncio.to_thread(encode,data.texts)
        return {'model':MODEL_KEY,'vectors':vectors,'max_tokens':manifest['max_tokens']}
    finally:
        gate.release()
