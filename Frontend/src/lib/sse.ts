export interface SseFrame {
  event: string;
  data: unknown;
}

/**
 * Incremental parser for Server-Sent-Event frames. Network chunks can split a frame anywhere,
 * so input is buffered until a blank line completes a frame. Malformed frames are skipped.
 */
export function createSseParser(onFrame: (frame: SseFrame) => void) {
  let buffer = "";

  const parseFrame = (raw: string) => {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of raw.split("\n")) {
      if (line.startsWith(":")) continue;
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
    }
    if (dataLines.length === 0) return;
    try {
      onFrame({ event, data: JSON.parse(dataLines.join("\n")) });
    } catch {
      // A frame that is not valid JSON is ignored rather than breaking the whole stream.
    }
  };

  return {
    push(chunk: string) {
      buffer += chunk.replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        parseFrame(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
      }
    },
  };
}
