import assert from 'node:assert/strict';
import test from 'node:test';
import {filterSaleProducts,searchSelection,saleStockRemaining} from '../src/saleProductSearch.ts';
import {readFileSync} from 'node:fs';

const products=[
  {id:'a',name:'Bolo de maçã',sku:'COT-ABC123',current_stock:0},
  {id:'b',name:'Bolo de chocolate',sku:'COT-DEF456',current_stock:3},
  {id:'c',name:'Ovo puro',sku:'OVO-123',current_stock:2},
].map(product=>({...product,sale_price:'10.00'}));

test('zero-stock products remain searchable and selectable',()=>{
  assert.equal(filterSaleProducts(products,'maca')[0].id,'a');
  assert.equal(searchSelection(products,'COT-ABC123'),'a');
  assert.equal(searchSelection(products,'bolo de maçã'),'a');
});
test('search ignores accents/case and accepts partial SKU and multiple terms',()=>{
  assert.equal(searchSelection(products,'  BOLO MACA  '),'a');
  assert.equal(searchSelection(products,'def456'),'b');
  assert.equal(filterSaleProducts(products,'bolo').length,2);
  assert.equal(searchSelection(products,'bolo'),'');
});
test('empty and unmatched queries clear selection without removing the catalog',()=>{
  assert.equal(filterSaleProducts(products,'').length,3);
  assert.equal(searchSelection(products,''),'');
  assert.deepEqual(filterSaleProducts(products,'inexistente'),[]);
  assert.equal(searchSelection(products,'inexistente'),'');
  assert.equal(products[0].id,'a');
});
test('selection does not bypass stock limits or double-count cart quantities',()=>{
  assert.equal(saleStockRemaining(products[0],0),0);
  assert.equal(saleStockRemaining(products[1],1),2);
  assert.equal(saleStockRemaining(products[1],3),0);
  assert.equal(saleStockRemaining(products[1],5),0);
  assert.equal(saleStockRemaining(undefined),0);
});

test('dropdown markup does not disable individual zero-stock options',()=>{
  // Guard the exact original regression in the native select, alongside the behavioral tests above.
  const source=readFileSync(new URL('../src/SaleProductPicker.tsx',import.meta.url),'utf8');
  assert.match(source,/<input[^>]*type="search"/);
  const options=source.match(/<option\b[^>]*>/g);
  assert.ok(options?.length);
  for(const option of options)assert.doesNotMatch(option,/\bdisabled\b/);
  assert.match(source,/value=\{product\.id\}/);
});
