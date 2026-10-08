import type { UserFacingError } from "./types";

export const MAX_UPLOAD_MB = 25;
export const ACCEPT_ATTRIBUTE =
  ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

const ALLOWED_EXTENSIONS = [".pdf", ".docx"];

/** First line of defence only. The server re-checks the real file contents. */
export function validateFile(file: File): UserFacingError | null {
  const name = file.name.toLowerCase();
  if (!ALLOWED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return {
      code: "UNSUPPORTED_TYPE",
      message: `Only PDF and DOCX files can be uploaded. "${file.name}" is not one of those.`,
    };
  }
  if (file.size === 0) {
    return { code: "EMPTY_FILE", message: "This file is empty (0 bytes)." };
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return {
      code: "FILE_TOO_LARGE",
      message: `This file is larger than the ${MAX_UPLOAD_MB} MB limit.`,
    };
  }
  return null;
}
