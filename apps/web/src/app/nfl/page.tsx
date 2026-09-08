import { SportPage } from "@/components/sport-page";

export const revalidate = 120;
export const metadata = { title: "NFL" };

export default function Page(props: { searchParams: Promise<{ date?: string }> }) {
  return <SportPage sport="nfl" searchParams={props.searchParams} />;
}
