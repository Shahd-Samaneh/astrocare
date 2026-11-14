// Owner pair, read from OWNERS.md at build time.
import raw from './OWNERS.md?raw';

export const OWNERS = raw.trim().split(/\r?\n/)[0];
