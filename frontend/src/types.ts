import type { components } from "./api.generated";

type Schemas = components["schemas"];

export type Brief = Schemas["BriefView"];
export type BriefDraft = Schemas["BriefCreate"];
export type BriefFields = Schemas["BriefFields"];
export type Today = Schemas["TodayView"];
export type Topic = Schemas["TopicView"];
