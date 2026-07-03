import "@testing-library/jest-dom/vitest";
import { Blob } from "node:buffer";

// jsdom's Blob does not implement .text()/.arrayBuffer(); Node's does, and
// download.ts only needs Blob for the download path, so restoring the Node
// implementation globally is safe here.
globalThis.Blob = Blob as unknown as typeof globalThis.Blob;
