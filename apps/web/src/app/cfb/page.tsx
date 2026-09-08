import { SportPage } from "@/components/sport-page";

export const revalidate = 120;
export const metadata = { title: "College Football" };

export default function Page(props: { searchParams: Promise<{ date?: string }> }) {
  return <SportPage sport="cfb" searchParams={props.searchParams} />;
}
