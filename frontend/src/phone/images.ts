import { decrypt } from "./crypto";
import type { PageFiles } from "./snapshot";

/** Every image of a snapshot, decrypted up front so the list shows whole, kept as object URLs until the page locks. */
export class PageImages {
  private readonly urls: ReadonlyMap<string, string>;

  private constructor(urls: ReadonlyMap<string, string>) {
    this.urls = urls;
  }

  static readonly none = new PageImages(new Map());

  /** Decrypts them in parallel; an image that fails to load is left out, as a missing file is. */
  static async open(files: PageFiles, key: CryptoKey, published: Record<string, string>): Promise<PageImages> {
    const loaded = await Promise.all(
      Object.entries(published).map(async ([url, file]) => {
        try {
          const image = await decrypt(await files.file(file), key);
          return [url, URL.createObjectURL(new Blob([image]))] as const;
        } catch {
          return null;
        }
      }),
    );
    return new PageImages(new Map(loaded.filter((entry) => entry !== null)));
  }

  url(path: string): string | null {
    return this.urls.get(path) ?? null;
  }

  release(): void {
    this.urls.forEach((url) => URL.revokeObjectURL(url));
  }
}
