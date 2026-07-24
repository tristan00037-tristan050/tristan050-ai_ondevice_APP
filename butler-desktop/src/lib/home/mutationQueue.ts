export class MutationQueue {
  private tails = new Map<string, Promise<unknown>>();

  enqueue<T>(key: string, operation: () => Promise<T>): Promise<T> {
    const previous = this.tails.get(key) ?? Promise.resolve();
    const current = previous.catch(() => undefined).then(operation);
    this.tails.set(key, current);
    void current.finally(() => {
      if (this.tails.get(key) === current) this.tails.delete(key);
    });
    return current;
  }

  idle(key: string): Promise<unknown> {
    return this.tails.get(key) ?? Promise.resolve();
  }
}
