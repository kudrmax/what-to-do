const LONG_LATIN_WORD = /[A-Za-zÀ-ɏ]{8,}/g;
const SOFT_HYPHEN = "­";
const MIN_PART = 3;

/**
 * Lets long Latin words, mostly names, break with a hyphen: the hyphenation dictionaries
 * know ordinary words but not "Shcherbakova", which otherwise breaks without one.
 */
export function softHyphenate(text: string): string {
  return text.replace(LONG_LATIN_WORD, (word) => {
    const head = word.slice(0, MIN_PART);
    const middle = word.slice(MIN_PART, word.length - MIN_PART);
    const tail = word.slice(word.length - MIN_PART);
    return head + [...middle].map((letter) => SOFT_HYPHEN + letter).join("") + SOFT_HYPHEN + tail;
  });
}
