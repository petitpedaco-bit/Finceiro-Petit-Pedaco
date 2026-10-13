export interface BankHistoryFilters { start_date:string;end_date:string;direction:string;treatment:string;search:string }
export const emptyBankFilters=():BankHistoryFilters=>({start_date:'',end_date:'',direction:'',treatment:'',search:''});
export function bankHistoryQuery(offset:number,filters:BankHistoryFilters):string {
  const query=new URLSearchParams({limit:'20',offset:String(offset)});
  for(const [key,value] of Object.entries(filters))if(value.trim())query.set(key,value.trim());
  return query.toString();
}
