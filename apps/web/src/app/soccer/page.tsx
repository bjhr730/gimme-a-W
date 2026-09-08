import { SportPage } from "@/components/sport-page";

export const revalidate = 120;
export const metadata = { title: "Soccer" };

export default function Page(props: { searchParams: Promise<{ date?: string }> }) {
  return <SportPage sport="soccer" searchParams={props.searchParams} />;
}
