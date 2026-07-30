import "dotenv/config";
import http from "node:http";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { registerPrompts } from "./prompts/index.js";
import { registerResources } from "./resources/index.js";
import { registerTools } from "./tools/index.js";

const PORT = parseInt(process.env["MCP_SERVER_PORT"] ?? "3000", 10);

function createServer(): McpServer {
  const server = new McpServer({
    name: "regai-mcp",
    version: "0.1.0",
  });
  registerTools(server);
  registerResources(server);
  registerPrompts(server);
  return server;
}

const sessions = new Map<string, { transport: StreamableHTTPServerTransport; server: McpServer }>();

const httpServer = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok" }));
    return;
  }

  const sessionId = req.headers["mcp-session-id"] as string | undefined;
  const rawBody = await readBody(req);
  // The SDK's handleRequest expects a pre-parsed JS object as parsedBody, not a raw Buffer.
  // Passing a Buffer makes it fail JSON-RPC schema validation with a -32700 parse error.
  let body: unknown;
  try {
    body = rawBody.length ? JSON.parse(rawBody.toString("utf-8")) : undefined;
  } catch {
    body = undefined;
  }

  if (sessionId && sessions.has(sessionId)) {
    const session = sessions.get(sessionId)!;
    await session.transport.handleRequest(req, res, body);
    return;
  }

  if (sessionId && !sessions.has(sessionId)) {
    res.writeHead(406, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "Unknown session" }));
    return;
  }

  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: () => crypto.randomUUID(),
    enableJsonResponse: true,
  });
  const server = createServer();

  transport.onclose = () => {
    const id = [...sessions.entries()].find(([, s]) => s.transport === transport)?.[0];
    if (id) sessions.delete(id);
  };

  await server.connect(transport);
  await transport.handleRequest(req, res, body);

  // Read the generated session id from the transport itself. The SDK writes the
  // mcp-session-id response header via its own (Hono) response path, not through
  // the Node res API, so res.getHeader("mcp-session-id") is undefined here.
  const newId = transport.sessionId;
  if (newId) sessions.set(newId, { transport, server });
});

function readBody(req: http.IncomingMessage): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

httpServer.listen(PORT, () => {
  console.log(`RegAI MCP server listening on port ${PORT.toString()}`);
});
