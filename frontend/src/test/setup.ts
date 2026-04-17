process.env.NODE_ENV = "development";
(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

import "@testing-library/jest-dom/vitest";
