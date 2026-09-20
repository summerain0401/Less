import type { components } from "./api.generated";
type Schema = components["schemas"];
export type Source = Schema["SourceView"];
export type Item = Schema["ItemView"];
export type Run = Schema["RunView"];
export type Detail = Schema["DetailView"];
export type Check = Schema["CheckView"];
export type Overview = Schema["OverviewView"];
