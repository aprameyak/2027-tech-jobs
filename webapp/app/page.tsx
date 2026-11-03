import { getAllListingsData } from '@/lib/listings';
import JobsClient from '@/components/JobsClient';

export default function Home() {
  const data = getAllListingsData();
  return <JobsClient data={data} />;
}
