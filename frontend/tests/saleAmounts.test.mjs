import test from 'node:test';
import assert from 'node:assert/strict';
import {cents,decimal,discountCents,calculateSale} from '../src/saleAmounts.ts';
const line=(price='100.00',quantity=1,discount='',discountType='FIXED')=>({product:{id:'test',name:'Produto teste',sale_price:price,current_stock:100},quantity,discount,discountType});

test('Brazilian decimal amounts, currency paste and fixed reais discounts use exact cents',()=>{
  assert.equal(cents('10,50'),1050n);assert.equal(cents('R$ 1.234,56'),123456n);
  const result=calculateSale([line('0.10',3)],'0,10','FIXED');
  assert.equal(result.net,20n);assert.equal(result.expected_net_total,'0.20');
  assert.equal(result.sale_discount_value,'0.10');
});
test('percent and item plus order discounts preserve the same order of calculation as server',()=>{
  const result=calculateSale([line('50.00',2,'10','PERCENTAGE')],'10','PERCENTAGE');
  assert.equal(result.gross,10000n);assert.equal(result.itemDiscount,1000n);
  assert.equal(result.saleDiscount,900n);assert.equal(result.net,8100n);
  assert.equal(result.discountTotal,1900n);assert.equal(result.sale_discount_type,'PERCENTAGE');
});
test('item fixed discount applies to the line total, not once per unit',()=>{
  const result=calculateSale([line('25.00',2,'5,00')],'','FIXED');
  assert.equal(result.net,4500n);assert.equal(result.items[0].discount_value,'5.00');
});
test('percentage midpoint rounds half up and 100 percent never produces negative totals',()=>{
  assert.equal(discountCents(5n,'PERCENTAGE','10'),1n);
  assert.equal(discountCents(5n,'PERCENTAGE','100'),5n);
  assert.equal(decimal(calculateSale([line()],'100','PERCENTAGE').net),'0.00');
});
test('invalid, negative, oversized discounts and stock quantities are rejected rather than hidden as zero',()=>{
  for(const value of ['-1','abc','10,123','1,2,3'])assert.throws(()=>cents(value));
  assert.throws(()=>calculateSale([line()],'101','PERCENTAGE'));
  assert.throws(()=>calculateSale([line()],'101','FIXED'));
  assert.throws(()=>calculateSale([line('10',0)],'','FIXED'));
});
