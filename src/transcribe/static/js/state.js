// The one mutable state object. Modules read and write it directly, then call their own render functions.

export const state = {
  recording: false, recId: null, recTitle: "", elapsed: 0, elapsedAt: 0,
  meetings: [], currentId: null, detail: null, busy: false,
  viewTimer: null, viewToken: 0, detailAt: 0, models: [],
};
