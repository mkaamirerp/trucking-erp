# Document Parser transport / execution designs

This folder contains designs about **how parser work is executed or transported**, not alternate semantic parsers.

## Architecture lock

TruckERP has **one shared Document Parser engine/pipeline with attached document profiles**. Rate Confirmation v2 is the first shipped profile; Fuel, Toll, and future document types attach their own profile/rules/schema/context to the same parser boundary.

Current semantic architecture lives in:

- `../TruckERP_Shared_Document_Parsing_Architecture.md`
- `../TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`

A job/queue/background-worker design may change **when and where** the shared parser runs. It must not create a second parser implementation or redefine profile semantics.

## Current design note

- `ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md` — **design only / not implemented**. Proposes moving the Load Page Rate Confirmation parse request from synchronous HTTP execution to a durable async job while preserving the same parser/profile result and workspace hydration contract.
