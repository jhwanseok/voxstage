import { describe, expect, it } from "vitest";
import { ApiError } from "./api";

describe("ApiError", () => {
  it("says which role is missing in plain Korean", () => {
    expect(new ApiError(403, { detail: { message: "this needs the publisher role", missing_role: "publisher" } }).message).toBe("이 작업은 게시 권한이 필요해요");
    expect(new ApiError(403, { detail: { message: "user is not active" } }).message).toBe("user is not active");
  });
});
