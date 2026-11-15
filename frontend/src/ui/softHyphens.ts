const LATIN_WORD = /[A-Za-zÀ-ɏ]{6,}/g;
const VOWEL = /[aeiouyà-æè-ïò-öø-ýāăąēĕėęěīĭįıōŏőūŭůűų]/i;
const DIGRAPHS = new Set(["sh", "ch", "th", "ph", "ck", "gh", "wh", "qu", "lj", "nj", "dž"]);
const ONSETS = new Set(["bl", "br", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl", "pr", "sc", "sk", "sl", "sm", "sn", "sp", "st", "sw", "tr", "tw", "wr"]);
const SOFT_HYPHEN = "\u00AD";
const MIN_HEAD = 2;
const MIN_TAIL = 3;

const isVowel = (letter: string) => VOWEL.test(letter);

/** Where a run of consonants between two vowels splits: before its last consonant, or before the pair that can start a syllable. */
function splitInRun(word: string, start: number, end: number): number {
  if (end - start === 1) return start;
  const lastPair = word.slice(end - 2, end).toLowerCase();
  const at = end - start >= 3 && ONSETS.has(lastPair) ? end - 2 : end - 1;
  return DIGRAPHS.has(word.slice(at - 1, at + 1).toLowerCase()) ? at - 1 : at;
}

/** Places between syllables, by the plain rules V-CV, VC-CV and VC-CCV, without splitting sh, ch, nj and the like. */
function syllableBreaks(word: string): number[] {
  const breaks: number[] = [];
  let i = 1;
  while (i < word.length) {
    if (isVowel(word[i]) || !isVowel(word[i - 1])) {
      i++;
      continue;
    }
    let end = i;
    while (end < word.length && !isVowel(word[end])) end++;
    if (end < word.length) {
      const at = splitInRun(word, i, end);
      if (at >= MIN_HEAD && word.length - at >= MIN_TAIL) breaks.push(at);
    }
    i = end;
  }
  return breaks;
}

/**
 * Lets long Latin words, mostly names, break between syllables with a hyphen: the page is Russian,
 * so the browser hyphenates only Russian words by itself, and "Shcherbakova" would break anywhere.
 */
export function softHyphenate(text: string): string {
  return text.replace(LATIN_WORD, (word) => {
    let out = "";
    let from = 0;
    for (const at of syllableBreaks(word)) {
      out += word.slice(from, at) + SOFT_HYPHEN;
      from = at;
    }
    return out + word.slice(from);
  });
}
