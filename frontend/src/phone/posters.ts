import { createContext, useContext, useEffect, useState } from "react";

import { decrypt } from "./crypto";
import type { PageFiles } from "./snapshot";

/** Posters fetched and decrypted the first time a card needs them, then kept as object URLs until the page locks. */
export class Posters {
  private readonly urls = new Map<string, Promise<string | null>>();
  private readonly made: string[] = [];
  private readonly files: PageFiles;
  private readonly key: CryptoKey;

  constructor(files: PageFiles, key: CryptoKey) {
    this.files = files;
    this.key = key;
  }

  url(path: string): Promise<string | null> {
    let url = this.urls.get(path);
    if (!url) {
      url = this.load(path);
      this.urls.set(path, url);
    }
    return url;
  }

  release(): void {
    this.made.forEach((url) => URL.revokeObjectURL(url));
    this.made.length = 0;
    this.urls.clear();
  }

  private async load(path: string): Promise<string | null> {
    try {
      const image = await decrypt(await this.files.file(path), this.key);
      const url = URL.createObjectURL(new Blob([image]));
      this.made.push(url);
      return url;
    } catch {
      return null;
    }
  }
}

export const PostersContext = createContext<Posters | null>(null);

export function usePoster(path: string | null | undefined): string | null {
  const posters = useContext(PostersContext);
  const [loaded, setLoaded] = useState<{ path: string; url: string | null } | null>(null);
  useEffect(() => {
    if (!path || !posters) return;
    let current = true;
    void posters.url(path).then((url) => current && setLoaded({ path, url }));
    return () => {
      current = false;
    };
  }, [path, posters]);
  return loaded && loaded.path === path ? loaded.url : null;
}
