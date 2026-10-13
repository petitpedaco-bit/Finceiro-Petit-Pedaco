import type { BankChoice } from './api';

export function defaultBankChoice(fingerprint:string):BankChoice {
  return {fingerprint,action:'BANK_ONLY',cash_transaction_id:null,category:'Outros / revisar',payment_method:'PIX',
    expense_nature:'UNCLASSIFIED',expense_behavior:'UNSPECIFIED',expense_context:'GENERAL',classification_reviewed:false};
}

export function invalidBankChoice(choice:BankChoice,direction:'INCOME'|'EXPENSE'):boolean {
  if(choice.action==='LINK')return !choice.cash_transaction_id;
  if(choice.action==='EXPENSE')return direction!=='EXPENSE'||!choice.category.trim()||choice.expense_nature!=='UNCLASSIFIED'&&!choice.classification_reviewed;
  return false;
}
