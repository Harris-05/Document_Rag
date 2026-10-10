"use client";

import { usePathname } from "next/navigation";
import { NavLinks } from "./NavLinks";

const LIBRARY_PREFIXES = ["/app", "/documents", "/conversations", "/comparisons"];

/** Marks "Library" as current on every page that belongs to the app. */
export function ActiveNav() {
  const pathname = usePathname();
  const inLibrary = LIBRARY_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
  return <NavLinks inLibrary={inLibrary} />;
}
