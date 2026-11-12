/* WINGS metadata preparation: deterministic, offline, display-independent. */
((root, factory) => {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.WINGS_METADATA = api;
})(globalThis, () => {
  "use strict";
  const FIELDS = ["sample_id", "host", "specimen_type", "collection_date", "state", "country", "latitude", "longitude"];
  const key = value => String(value ?? "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const text = value => String(value ?? "");
  const ALIASES = {
    sample_id: ["sample", "sample id", "sample name", "id", "sample identifier"],
    host: ["host", "host code", "host common name", "host species", "species", "bird", "bird species"],
    specimen_type: ["specimen type", "sample type", "specimen", "material"],
    collection_date: ["collection date", "date collected", "sample date", "date"],
    state: ["state", "province", "territory", "state province", "province territory", "region"],
    country: ["country", "country code"], latitude: ["latitude", "lat"], longitude: ["longitude", "lon", "long", "lng"]
  };
  const headerAliases = new Map(Object.entries(ALIASES).flatMap(([field, values]) => [field, ...values].map(value => [key(value), field])));
  const suggestHeader = header => headerAliases.get(key(header)) || header;
  const stripFastq = name => text(name).replace(/\.(?:fastq|fq)(?:\.gz)?$/i, "");
  const fastqExtension = name => text(name).match(/\.(?:fastq|fq)(?:\.gz)?$/i)?.[0].toLowerCase() || "";

  function parseTable(input, delimiter = "auto", limits = {}) {
    const source = text(input).replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n");
    const maxLength=limits.maxLength ?? 10*1024*1024,maxRows=limits.maxRows ?? 10000;
    if (source.length > maxLength) throw new Error("Metadata exceeds the supported file size.");
    if (!source.trim()) throw new Error("The table is empty.");
    if (delimiter === "auto") {
      const counts = new Map([["\t",0],[",",0],[";",0]]);let quoted=false;
      for (let i=0;i<source.length;i++) {
        const c=source[i];
        if (c==='"') {if (quoted && source[i+1]==='"') i++;else quoted=!quoted;}
        else if (!quoted && c==='\n') break;
        else if (!quoted && counts.has(c)) counts.set(c,counts.get(c)+1);
      }
      delimiter=[...counts].sort((a,b)=>b[1]-a[1])[0][0];
    }
    if (!["\t",",",";"].includes(delimiter)) throw new Error("Choose tab, comma, or semicolon as the separator.");
    const records=[];let row=[],field="",quoted=false,closed=false;
    const finishField=()=>{row.push(field);field="";closed=false;};
    const finishRow=()=>{finishField();if(row.some(value=>value.trim())) records.push(row);row=[];};
    for (let i=0;i<source.length;i++) {
      const c=source[i];
      if (quoted) {
        if(c==='"') {if(source[i+1]==='"'){field+='"';i++;}else{quoted=false;closed=true;}}
        else field+=c;
      } else if(c===delimiter) finishField();
      else if(c==='\n') finishRow();
      else if(c==='"' && !field && !closed) quoted=true;
      else if(closed && c===' ') continue;
      else if(closed || c==='"') throw new Error("Invalid quoting near row " + (records.length+1) + ".");
      else field+=c;
      if(records.length>maxRows+1) throw new Error("The wizard supports up to 10,000 sample rows.");
    }
    if(quoted) throw new Error("A quoted field was not closed.");
    if(field || row.length || closed) finishRow();
    const headers=(records.shift() || []).map(value=>value.trim());
    if(!headers.length || headers.some(value=>!value)) throw new Error("Every column needs a header.");
    if(new Set(headers.map(value=>value.toLowerCase())).size!==headers.length) throw new Error("The table has duplicate column headers.");
    const warnings=[];
    const rows=records.map((values,index)=>{
      if(values.length>headers.length) throw new Error(`Row ${index+1} has more cells than the header; check the separator or quoting.`);
      if(values.length<headers.length) warnings.push(`Row ${index+1}: missing trailing cells were left blank.`);
      return headers.map((_,i)=>values[i] ?? "");
    });
    if(rows.length>maxRows) throw new Error("The wizard supports up to 10,000 sample rows.");
    return {headers,rows,delimiter,warnings};
  }

  function mapTable(parsed, mapping = parsed.headers.map(suggestHeader)) {
    const targets=mapping.map(value=>text(value).trim());
    if(targets.length!==parsed.headers.length || targets.some(value=>!value)) throw new Error("Map each input column.");
    if(new Set(targets.map(value=>value.toLowerCase())).size!==targets.length) throw new Error("Two input columns map to the same output column. Keep one as an extra column.");
    const fields=[...FIELDS,...targets.filter(field=>!FIELDS.includes(field))];
    const rows=parsed.rows.map(values=>Object.fromEntries(fields.map(field=>[field,targets.includes(field)?values[targets.indexOf(field)]:""])));
    return {fields,rows};
  }

  function buildIndex(reference) {
    const hosts=new Map(),names=new Map(),countries=new Map(),regions=new Map();
    const push=(map,k,value)=>{if(!map.has(k))map.set(k,[]);map.get(k).push(value);};
    for(const host of reference.hosts || []) {push(hosts,key(host.code),host);push(names,key(host.name),host);}
    for(const country of reference.countries || []) for(const alias of [country.name,country.alpha2,country.alpha3,...(country.aliases||[])]) countries.set(key(alias),country);
    for(const [alias,code] of Object.entries({"United States of America":"USA",US:"USA",USA:"USA",UK:"GBR","Great Britain":"GBR","South Korea":"KOR","North Korea":"PRK",Russia:"RUS",Turkey:"TUR","Viet Nam":"VNM"})) {
      const country=(reference.countries||[]).find(item=>item.alpha3===code);if(country)countries.set(key(alias),country);
    }
    for(const region of reference.regions || []) for(const alias of [region.name,region.code]) regions.set(region.country+":"+key(alias),region);
    return {hosts,names,countries,regions};
  }
  function hostMatch(value,index) {
    const matches=index.hosts.get(key(value)) || index.names.get(key(value));
    if(!matches || new Set(matches.map(item=>key(item.name))).size!==1) return null;
    return matches[0];
  }
  const countryMatch=(value,index)=>index.countries.get(key(value)) || null;
  const regionMatch=(value,country,index)=>{const nation=countryMatch(country,index);return nation?index.regions.get(nation.alpha3+":"+key(value)) || null:null;};
  function validDate(value) {
    if(!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const [year,month,day]=value.split("-").map(Number);
    const d=new Date(0);d.setUTCFullYear(year,month-1,day);d.setUTCHours(0,0,0,0);
    return year>=1 && d.getUTCFullYear()===year && d.getUTCMonth()===month-1 && d.getUTCDate()===day;
  }
  function normalizeDate(value,format="ask") {
    const original=text(value).trim();if(!original || validDate(original))return original;
    const iso=original.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if(iso){const padded=`${iso[1]}-${iso[2].padStart(2,"0")}-${iso[3].padStart(2,"0")}`;return validDate(padded)?padded:original;}
    const match=original.match(/^(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{4})$/);
    if(!match)return original;
    const first=Number(match[1]),second=Number(match[2]);let mode=format;
    if(mode==="ask") {if(first>12 && second<=12)mode="DMY";else if(second>12 && first<=12)mode="MDY";else if(first===second)mode="DMY";else return original;}
    const day=mode==="DMY"?first:second,month=mode==="DMY"?second:first;
    const result=`${match[3]}-${String(month).padStart(2,"0")}-${String(day).padStart(2,"0")}`;
    return validDate(result)?result:original;
  }
  function normalizeCoordinate(value,axis) {
    const original=text(value).trim(),m=original.match(/^([+]?\d+(?:\.\d+)?)\s*°?\s*([NSEW])$/i);
    if(!m || !(axis==="latitude"?/^[NS]$/i:/^[EW]$/i).test(m[2]))return original;
    return (/^[SW]$/i.test(m[2])?"-":"")+m[1].replace(/^\+/,"");
  }
  function normalizeRows(rows,index,phase="all",options={}) {
    const changes=[];
    const result=rows.map((row,i)=>{
      const copy={...row};
      const set=(field,value)=>{if(text(row[field])!==value){copy[field]=value;changes.push({row:i+1,field,before:text(row[field]),after:value});}};
      if(["ids","all"].includes(phase))set("sample_id",text(row.sample_id).trim());
      if(["hosts","all"].includes(phase)){const value=text(row.host).trim();set("host",hostMatch(value,index)?.code || value);}
      if(["collection","all"].includes(phase)) {
        const country=text(row.country).trim(),nation=countryMatch(country,index);
        set("country",nation?.alpha3 || country);
        const region=text(row.state).trim();set("state",regionMatch(region,nation?.alpha3||country,index)?.name || region);
        set("collection_date",normalizeDate(row.collection_date,options.dateFormat));
        for(const axis of ["latitude","longitude"])set(axis,normalizeCoordinate(row[axis],axis));
        const specimen=text(row.specimen_type).trim().replace(/\s+/g," ");
        const known=["Dry (Oral+Cloacal)","Dry (Oral)","Dry (Cloacal)"];
        set("specimen_type",known.find(value=>key(value)===key(specimen)) || specimen);
      }
      return copy;
    });
    return {rows:result,changes};
  }
  function suggestIds(value,filenames,barcode="") {
    const ids=filenames.map(stripFastq),exact=ids.filter(id=>key(id)===key(value));
    if(text(value).trim() && exact.length)return [...new Set(exact)];
    const code=(text(barcode)||text(value)).match(/barcode\d+/i)?.[0].toLowerCase();
    return code?[...new Set(ids.filter(id=>id.toLowerCase().match(/barcode\d+/)?.[0]===code))]:[];
  }
  function validate(rows,filenames,index) {
    const errors=[],warnings=[],seen=new Set(),readIds=filenames.map(stripFastq),reads=new Set(readIds);
    const add=(list,row,field,message,code)=>list.push({row,field,message,code});
    if(!rows.length)add(errors,0,"sample_id","Add at least one sample.","no_rows");
    if(rows.length>10000)add(errors,0,"sample_id","The wizard supports up to 10,000 sample rows.","row_limit");
    const extensions=filenames.map(fastqExtension);
    if(extensions.some(ext=>!ext))add(errors,0,"FASTQ","Choose .fastq, .fq, .fastq.gz, or .fq.gz files.","extension");
    if(new Set(extensions).size>1)add(errors,0,"FASTQ","WINGS requires the same FASTQ extension for every file.","mixed_extensions");
    if(reads.size!==readIds.length)add(errors,0,"FASTQ","Selected files produce duplicate sample IDs.","duplicate_fastq");
    let complete=0;
    rows.forEach((row,i)=>{
      const n=i+1,id=text(row.sample_id),country=countryMatch(row.country,index),host=hostMatch(row.host,index);
      if(!id.trim())add(errors,n,"sample_id","Enter a sample ID.","empty_id");
      else {
        if(id!==id.trim())add(errors,n,"sample_id","Remove leading or trailing spaces from this ID.","id_spaces");
        if(seen.has(id))add(errors,n,"sample_id","Duplicate sample ID: "+id,"duplicate_id");
        seen.add(id);
        if(filenames.length && !reads.has(id))add(errors,n,"sample_id","No FASTQ filename matches this ID exactly.","unmatched_id");
      }
      if(row.collection_date && !validDate(row.collection_date))add(errors,n,"collection_date","Use a valid YYYY-MM-DD date; choose the source date format for ambiguous dates.","date");
      for(const [axis,limit] of [["latitude",90],["longitude",180]])if(text(row[axis]).trim() && (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(text(row[axis]).trim()) || !Number.isFinite(Number(row[axis])) || Math.abs(Number(row[axis]))>limit)) add(errors,n,axis,`Enter a finite number from -${limit} to ${limit}.`,"coordinate");
      for(const field of FIELDS.slice(1))if(!text(row[field]).trim())add(warnings,n,field,"Not recorded; complete this field if known.","missing_detail");
      if(text(row.host).trim() && !host)add(warnings,n,"host","Host is not recognized in the WINGS dictionary; review the species or code.","unknown_host");
      if(text(row.country).trim() && !country)add(warnings,n,"country","Country is not recognized; review the name or ISO code.","unknown_country");
      if(text(row.state).trim() && country && ["USA","CAN"].includes(country.alpha3) && !regionMatch(row.state,row.country,index))add(warnings,n,"state","Region does not match a US state/DC or Canadian province/territory for this country.","unknown_region");
      if(Boolean(text(row.latitude).trim())!==Boolean(text(row.longitude).trim()))add(warnings,n,"coordinates","Supply both latitude and longitude when known.","coordinate_pair");
      if(FIELDS.slice(1).every(field=>text(row[field]).trim()) && host && country && !errors.some(issue=>issue.row===n) && !warnings.some(issue=>issue.row===n))complete++;
    });
    const missingReads=readIds.filter(id=>!seen.has(id));
    for(const id of missingReads)add(errors,0,"sample_id","FASTQ has no metadata row: "+id,"missing_metadata");
    if(!filenames.length)add(warnings,0,"FASTQ","FASTQ matching is pending. Select sequencing files to confirm the sample IDs.","reads_pending");
    return {errors,warnings,complete,total:rows.length,missingReads,exactMatch:filenames.length>0 && !errors.some(issue=>["empty_id","id_spaces","duplicate_id","unmatched_id","missing_metadata","extension","mixed_extensions","duplicate_fastq"].includes(issue.code))};
  }
  function toTSV(fields,rows) {
    const quote=value=>{const str=text(value);return /["\t\r\n]/.test(str)?'"'+str.replace(/"/g,'""')+'"':str;};
    return [fields,...rows.map(row=>fields.map(field=>text(row[field])))].map(values=>values.map(quote).join("\t")).join("\n")+"\n";
  }
  function inspectIds(source) {
    if(text(source).startsWith("\uFEFF"))throw new Error("Use Create or fix metadata to remove the UTF-8 BOM, then select the exported TSV.");
    const parsed=parseTable(source,"\t",{maxLength:25*1024*1024,maxRows:Infinity}),column=parsed.headers.indexOf("sample_id");
    if(column<0)throw new Error("Metadata must contain a sample_id column.");
    const ids=parsed.rows.map(row=>row[column].trim());
    if(!ids.length)throw new Error("Metadata contains no sample_id values.");
    if(ids.some(id=>!id))throw new Error("Metadata contains an empty sample_id.");
    if(new Set(ids).size!==ids.length)throw new Error("Metadata contains duplicate sample_id values.");
    return ids;
  }
  return {FIELDS,key,suggestHeader,stripFastq,fastqExtension,parseTable,mapTable,buildIndex,hostMatch,countryMatch,regionMatch,validDate,normalizeDate,normalizeRows,suggestIds,validate,toTSV,inspectIds};
});
