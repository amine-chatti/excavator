# Excavator Field Notebook

## Install

Run `npm install` from `frontend/`.

## Run

Run `npm run dev`. The app expects the backend at `http://127.0.0.1:8000`; set `VITE_API_BASE_URL` to use another API address.

## Test

Run `npm test` for the Vitest suite. Requests are mocked; the tests do not use the network.

## Baseline label

The oldest visible `added` point is the start of the analyzed history window. It is not proof the symbol was born then; its dashed bedrock edge is labeled “history window starts here, real birth may be earlier”.

## Design

The dark field notebook uses soil, bone, ochre, rust, clay, and moss. Adjust palette and layout in `src/index.css`; shared reveal timing and variants live in `src/motion.ts`.
